"""
HKY Estates V2 - AI Opportunity Agent
Akış: kaynak → toplayıcı → kuyruk → normalizasyon → veritabanı → piyasa analizi → NLP → skor → sıralama → bildirim.
Her kayıt işlendiği anda kaydedilir; duraklatılan veya kesilen görev kaldığı yerden devam eder.
"""

import threading
import traceback
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import session_scope
from ..events import bus
from ..filters import apply_listing_filters, unmet_opportunity_flags
from ..models import (
    AgentJob,
    AgentJobItem,
    AgentJobLog,
    DataSource,
    DeadLetter,
    Listing,
    ListingDescription,
    MarketBenchmark,
    OpportunityReport,
    OpportunityScore,
    utcnow,
)
from ..network.client import AccessDeniedError, BlockedHostError, NetworkError, RateLimitedError, RequestCancelled
from ..providers.base import STATE_ACCESS_DENIED, STATE_ERROR, ProviderUnavailable
from ..providers.registry import build_client_factory, build_provider
from ..schemas import CONFIDENCE_MINIMUMS, AppSettings, ListingFilters
from ..security import redact
from ..settings_store import load_settings, proxy_password
from . import scorer
from .ingest import mark_near_duplicates, mark_stale, upsert_listing
from .market import MarketAnalyzer, load_pool, market_window, to_pool_item
from .nlp import RuleBasedAnalyzer, TfIdfIndex
from .normalizer import NormalizationError, normalize_record
from .notifier import maybe_notify
from .report import build_report

STAGES = ("collect", "ingest", "analyze", "rank")
STAGE_WEIGHTS = {"collect": (0, 15), "ingest": (15, 40), "analyze": (40, 98), "rank": (98, 100)}
ACTIVE_STATES = ("queued", "running", "pausing", "stopping")
PROGRESS_EVERY = 10


class JobPaused(Exception):
    pass


class JobStopped(Exception):
    pass


def job_payload(job: AgentJob) -> Dict:
    return {
        "id": job.id, "profile_name": job.profile_name, "source_keys": job.source_keys, "status": job.status,
        "stage": job.stage, "examined": job.examined, "processed": job.processed, "opportunities": job.opportunities,
        "failed_requests": job.failed_requests, "progress": round(job.progress, 1), "last_action": job.last_action,
        "error": job.error, "filters": job.filters,
        "created_at": job.created_at.isoformat() + "Z",
        "started_at": job.started_at.isoformat() + "Z" if job.started_at else None,
        "finished_at": job.finished_at.isoformat() + "Z" if job.finished_at else None,
    }


class AgentRunner:
    def __init__(self, job_id: str, control: "JobControl", today: Optional[date] = None) -> None:
        self.job_id = job_id
        self.control = control
        self.today = today or date.today()
        self.analyzer = RuleBasedAnalyzer()

    # --- yardımcılar -------------------------------------------------------------------------

    def _log(self, db: Session, message: str, level: str = "info") -> None:
        db.add(AgentJobLog(job_id=self.job_id, level=level, message=redact(message)))
        job = db.get(AgentJob, self.job_id)
        job.last_action = redact(message)[:300]
        db.commit()
        bus.publish("job.log", {"job_id": self.job_id, "level": level, "message": redact(message), "at": utcnow().isoformat() + "Z"})

    def _publish(self, job: AgentJob) -> None:
        bus.publish("job.updated", job_payload(job))

    def _checkpoint(self) -> None:
        if self.control.stop.is_set():
            raise JobStopped()
        if self.control.pause.is_set():
            raise JobPaused()

    def _progress(self, db: Session, stage: str, done: int, total: int) -> None:
        start, end = STAGE_WEIGHTS[stage]
        job = db.get(AgentJob, self.job_id)
        job.progress = start + (end - start) * (done / total if total else 1)
        db.commit()
        self._publish(job)

    def _item_counts(self, db: Session, kind: str) -> Dict[str, int]:
        rows = db.execute(
            select(AgentJobItem.status, func.count()).where(AgentJobItem.job_id == self.job_id, AgentJobItem.kind == kind).group_by(AgentJobItem.status)
        )
        return {status: count for status, count in rows}

    # --- yaşam döngüsü -----------------------------------------------------------------------

    def run(self) -> None:
        with session_scope() as db:
            job = db.get(AgentJob, self.job_id)
            job.status, job.error = "running", None
            job.started_at = job.started_at or utcnow()
            db.commit()
            self._log(db, "Görev başladı." if job.stage == "collect" else f"Görev '{job.stage}' aşamasından devam ediyor.")
            settings = AppSettings.model_validate(job.settings_snapshot)
            filters = ListingFilters.model_validate(job.filters)

        try:
            for stage in STAGES[STAGES.index(job.stage) :]:
                with session_scope() as db:
                    db.get(AgentJob, self.job_id).stage = stage
                    db.commit()
                getattr(self, f"_stage_{stage}")(filters, settings)
            failure = self._collect_failure()
            self._finish("failed" if failure else "completed", failure)
        except JobPaused:
            self._finish("paused")
        except JobStopped:
            # Durdurmada tamamlanan skorlar korunur ve sıralanır.
            self._stage_rank(filters, settings)
            self._finish("stopped")
        except Exception as exc:  # pragma: no cover - beklenmeyen hata kaydedilir
            with session_scope() as db:
                self._log(db, f"Beklenmeyen hata: {exc}", "error")
                self._log(db, traceback.format_exc()[-1500:], "debug")
            self._finish("failed", str(exc))

    def _finish(self, status: str, error: Optional[str] = None) -> None:
        with session_scope() as db:
            job = db.get(AgentJob, self.job_id)
            job.status = status
            job.error = redact(error)[:1000] if error else job.error
            if status in ("completed", "stopped", "failed"):
                job.finished_at = utcnow()
            if status == "completed":
                job.progress = 100
            db.commit()
            messages = {
                "completed": f"Görev tamamlandı: {job.opportunities} fırsat bulundu.",
                "paused": "Görev duraklatıldı; işlenen kayıtlar kaydedildi.",
                "stopped": "Görev durduruldu; tamamlanan sonuçlar kaydedildi.",
                "failed": "Görev hata ile sonlandı.",
            }
            self._log(db, messages[status], "error" if status == "failed" else "info")
            self._publish(job)

    # --- 1. toplama --------------------------------------------------------------------------

    def _stage_collect(self, filters: ListingFilters, settings: AppSettings) -> None:
        with session_scope() as db:
            job = db.get(AgentJob, self.job_id)
            source_keys, state = list(job.source_keys), dict(job.collect_state or {})
            password = proxy_password(db)

        for key in source_keys:
            if state.get(key, {}).get("done"):
                continue
            with session_scope() as db:
                source = db.scalar(select(DataSource).where(DataSource.key == key))
                self._log(db, f"{source.name} kaynağından veri toplanıyor.")
            factory = build_client_factory(
                source, settings, password,
                on_failure=self._dead_letter(key), on_request_failed=self._count_failure,
                should_cancel=lambda: self.control.stop.is_set() or self.control.pause.is_set(),
            )
            provider = build_provider(source, factory)
            cursor = state.get(key, {}).get("cursor")
            try:
                for page in provider.fetch(filters, cursor):
                    added = self._enqueue(key, page.records, provider.is_demo)
                    state[key] = {"cursor": page.next_cursor, "done": page.next_cursor is None}
                    with session_scope() as db:
                        job = db.get(AgentJob, self.job_id)
                        job.collect_state = dict(state)
                        db.commit()
                        self._log(db, f"{source.name}: {len(page.records)} kayıt alındı, {added} yeni kuyruğa eklendi.")
                    self._checkpoint()
                state[key] = {"cursor": None, "done": True}
            except (ProviderUnavailable, AccessDeniedError, RateLimitedError, BlockedHostError) as exc:
                self._source_failed(key, exc, state)
            except RequestCancelled:
                self._checkpoint()
                raise
            except NetworkError as exc:
                self._source_failed(key, exc, state)
            with session_scope() as db:
                job = db.get(AgentJob, self.job_id)
                job.collect_state = dict(state)
                db.commit()
            self._checkpoint()

        with session_scope() as db:
            counts = self._item_counts(db, "ingest")
            self._progress(db, "collect", 1, 1)
            if not counts:
                self._log(db, "Seçili kaynaklardan yeni kayıt gelmedi; mevcut veritabanı analiz edilecek.", "warning")

    def _collect_failure(self) -> Optional[str]:
        """Tüm kaynaklar hata verdiyse ve analiz edilecek ilan kalmadıysa görev başarılı sayılmaz."""
        with session_scope() as db:
            job = db.get(AgentJob, self.job_id)
            state = job.collect_state or {}
            errors = [state.get(key, {}).get("error") for key in job.source_keys]
            if job.processed or not errors or not all(errors):
                return None
        return "Seçili kaynaklardan ilan alınamadığı için analiz yapılamadı. " + errors[0]

    def _source_failed(self, key: str, exc: Exception, state: Dict) -> None:
        state[key] = {**state.get(key, {}), "done": True, "error": str(exc)}
        with session_scope() as db:
            source = db.scalar(select(DataSource).where(DataSource.key == key))
            if isinstance(exc, AccessDeniedError):
                source.status = STATE_ACCESS_DENIED
            elif not isinstance(exc, ProviderUnavailable):
                source.status = STATE_ERROR
            source.status_message, source.last_checked_at = redact(exc)[:500], utcnow()
            db.commit()
            self._log(db, f"{source.name}: {exc}", "error")

    def _dead_letter(self, key: str):
        def record(url: str, status_code: Optional[int], error: str, attempts: int) -> None:
            with session_scope() as db:
                db.add(DeadLetter(job_id=self.job_id, source_key=key, url=url, status_code=status_code, error=error, attempts=attempts))
                db.commit()

        return record

    def _count_failure(self) -> None:
        with session_scope() as db:
            db.execute(update(AgentJob).where(AgentJob.id == self.job_id).values(failed_requests=AgentJob.failed_requests + 1))
            db.commit()

    def _enqueue(self, source_key: str, records: List[Dict], is_demo: bool) -> int:
        added = 0
        with session_scope() as db:
            for record in records:
                listing_id = str(record.get("İlan No") or record.get("id") or record.get("_import_ref") or "").strip()
                if not listing_id:
                    continue
                db.add(AgentJobItem(job_id=self.job_id, kind="ingest", key=f"{source_key}:{listing_id}"[:180], payload={"source": source_key, "demo": is_demo, "raw": record}))
                try:
                    db.commit()
                    added += 1
                except IntegrityError:
                    db.rollback()
        return added

    # --- 2. normalizasyon ve kayıt -----------------------------------------------------------

    def _stage_ingest(self, filters: ListingFilters, settings: AppSettings) -> None:
        with session_scope() as db:
            pending = list(db.scalars(select(AgentJobItem.id).where(AgentJobItem.job_id == self.job_id, AgentJobItem.kind == "ingest", AgentJobItem.status == "pending").order_by(AgentJobItem.id)))
            total = sum(self._item_counts(db, "ingest").values())
            done = total - len(pending)
            if pending:
                self._log(db, f"{len(pending)} kayıt normalize edilip veritabanına yazılacak.")

        failures = 0
        for position, item_id in enumerate(pending, start=1):
            self._checkpoint()
            with session_scope() as db:
                item = db.get(AgentJobItem, item_id)
                payload = item.payload
                try:
                    record = normalize_record(payload["raw"], payload["source"], payload["demo"], self.today)
                    listing, created, price_changed = upsert_listing(db, record, self.job_id)
                    item.status, item.listing_id = "done", listing.id
                    if price_changed:
                        self._log(db, f"Fiyat değişikliği kaydedildi: {listing.source_listing_id}")
                except NormalizationError as exc:
                    db.rollback()
                    item = db.get(AgentJobItem, item_id)
                    item.status, item.error = "failed", str(exc)
                    failures += 1
                job = db.get(AgentJob, self.job_id)
                job.examined = done + position
                db.commit()
                if position % PROGRESS_EVERY == 0 or position == len(pending):
                    self._progress(db, "ingest", done + position, total)

        with session_scope() as db:
            if failures:
                self._log(db, f"{failures} kayıt eksik/okunamaz olduğu için atlandı (ilan no veya fiyat yok).", "warning")
            listing_ids = list(db.scalars(select(AgentJobItem.listing_id).where(AgentJobItem.job_id == self.job_id, AgentJobItem.kind == "ingest", AgentJobItem.listing_id.is_not(None))))
            duplicates = mark_near_duplicates(db, listing_ids)
            stale = mark_stale(db, self.today)
            if duplicates or stale:
                self._log(db, f"{duplicates} yakın kopya ilan işaretlendi, {stale} eski ilan pasife alındı.")

    # --- 3. piyasa analizi, NLP ve skor ------------------------------------------------------

    def _stage_analyze(self, filters: ListingFilters, settings: AppSettings) -> None:
        agent, is_demo = settings.agent, filters.data_mode == "demo"
        with session_scope() as db:
            if not self._item_counts(db, "score"):
                candidate_ids = list(db.scalars(apply_listing_filters(select(Listing.id), filters, self.today).order_by(Listing.id)))
                db.add_all(AgentJobItem(job_id=self.job_id, kind="score", key=str(lid), listing_id=lid) for lid in candidate_ids)
                db.commit()
                self._log(db, f"Fırsat aralığında filtrelere uyan {len(candidate_ids)} aday ilan analiz edilecek.")
            pending = list(db.scalars(select(AgentJobItem.id).where(AgentJobItem.job_id == self.job_id, AgentJobItem.kind == "score", AgentJobItem.status == "pending").order_by(AgentJobItem.id)))
            total = sum(self._item_counts(db, "score").values())
            done = total - len(pending)

            start, end = market_window(self.today, filters.market_window_days, filters.market_from, filters.market_to)
            pool = load_pool(db, is_demo, start, end)
            if pool:
                coverage = (self.today - min(item.listed_at for item in pool)).days
                if coverage < filters.market_window_days * 0.5:
                    self._log(db, f"Piyasa geçmişi yalnızca {coverage} günü kapsıyor; {filters.market_window_days} günlük veri yok, güven seviyesi düşürüldü.", "warning")
            else:
                self._log(db, "Piyasa analiz aralığında emsal ilan yok; fiyat avantajı hesaplanamayacak.", "warning")
            analyzer = MarketAnalyzer(pool, self.today, start, end, agent.min_comparables, agent.analysis_depth)
            candidate_scope = select(AgentJobItem.listing_id).where(AgentJobItem.job_id == self.job_id, AgentJobItem.kind == "score")
            texts = db.execute(
                select(Listing.title, ListingDescription.text)
                .join(ListingDescription, ListingDescription.listing_id == Listing.id, isouter=True)
                .where(Listing.id.in_(candidate_scope))
            )
            tfidf = TfIdfIndex(f"{title} {text or ''}" for title, text in texts)

        benchmarks: Dict[str, int] = {}
        for position, item_id in enumerate(pending, start=1):
            self._checkpoint()
            with session_scope() as db:
                item = db.get(AgentJobItem, item_id)
                listing = db.get(Listing, item.listing_id)
                if listing is None:
                    item.status = "failed"
                    db.commit()
                    continue
                score = self._evaluate(db, listing, analyzer, tfidf, filters, settings, benchmarks)
                item.status = "done"
                job = db.get(AgentJob, self.job_id)
                job.processed = done + position
                if score.is_opportunity:
                    job.opportunities += 1
                db.commit()
                if score.is_opportunity:
                    bus.publish("opportunity.found", {"job_id": self.job_id, "score_id": score.id, "listing_id": listing.id, "score": score.score, "is_demo": listing.is_demo})
                    maybe_notify(db, job.created_by, listing, score, settings.notifications)
                if position % PROGRESS_EVERY == 0 or position == len(pending):
                    self._progress(db, "analyze", done + position, total)

    def _evaluate(self, db: Session, listing: Listing, analyzer: MarketAnalyzer, tfidf: TfIdfIndex, filters: ListingFilters, settings: AppSettings, benchmarks: Dict[str, int]) -> OpportunityScore:
        agent = settings.agent
        # Tarihsiz ilan aday olabilir ama emsal havuzuna hiç girmez (load_pool tarih şartı arar).
        subject = to_pool_item(listing)
        description = listing.description.text if listing.description else ""
        analysis = self.analyzer.analyze(listing.title, description, agent.nlp_sensitivity)
        analysis.terms = tfidf.top_terms(f"{listing.title} {description}")

        comparables = analyzer.find_comparables(subject)
        confidence = analyzer.confidence(comparables, filters.market_window_days)
        confidence = round(confidence * (0.85 + listing.data_quality / 100 * 0.15), 1)

        discount = reference_value = market_median = market_avg = gap = None
        cheapest_region = False
        if comparables.sufficient and comparables.stats:
            stats = comparables.stats
            own = listing.price_per_m2 if comparables.kind == "unit" else float(listing.price)
            # Tek yerde yuvarlanır: kart, rapor ve bildirim aynı değeri gösterir.
            discount = round(scorer.discount_percent(stats.median, own), 1)
            reference_value = stats.median
            multiplier = listing.m2_gross if comparables.kind == "unit" else 1
            market_median, market_avg = stats.median * multiplier, stats.mean * multiplier
            gap = market_median - listing.price
            cheaper_than = sum(1 for o in comparables.items if (o.unit if comparables.kind == "unit" else o.price) > own)
            cheapest_region = cheaper_than / len(comparables.items) >= 1 - scorer.CHEAPEST_REGION_SHARE

        price_score = scorer.price_advantage_score(discount)
        fresh_score = scorer.freshness_score(listing.listed_at, self.today, filters.opportunity_window_days or 14)
        total = scorer.opportunity_score(price_score, analysis.score, fresh_score)
        risk = scorer.assess_risk(listing, analysis, discount, confidence)
        gross_yield = analyzer.gross_yield(subject)

        min_conf = CONFIDENCE_MINIMUMS[filters.min_confidence] if filters.min_confidence else 0.0
        eligible, reason = scorer.is_eligible(
            total, discount, confidence, risk.suspicious, comparables.stats.count if comparables.stats else 0,
            max(agent.min_score, filters.min_score or 0), max(agent.min_advantage, filters.min_advantage or 0),
            agent.min_comparables, min_conf,
        )
        warnings = list(risk.warnings)
        if not comparables.sufficient:
            warnings.insert(0, f"Yetersiz emsal: en fazla {comparables.best_count} benzer ilan bulundu (gereken {agent.min_comparables}).")
        elif comparables.coverage_days < filters.market_window_days * 0.5:
            warnings.append(f"Emsal verisi yalnızca {comparables.coverage_days} günü kapsıyor.")

        keys = set(analysis.keys)
        if listing.price_drop_pct:
            keys.add("price_drop")
        if cheapest_region:
            keys.add("cheapest_region")
        if (gross_yield and gross_yield >= scorer.HIGH_YIELD_PCT) or ("investment" in keys and (discount or 0) > 0):
            keys.add("high_investment")

        # Ana sayfada işaretlenen fırsat kutuları (acil, kelepir, medyan altı...) taramada da zorunludur.
        unmet = unmet_opportunity_flags(filters, keys, listing.price, market_avg, market_median, listing.price_drop_pct)
        if eligible and unmet:
            eligible, reason = False, "Seçili fırsat filtresi karşılanmadı: " + ", ".join(unmet)

        segment_key, _label, _predicate = analyzer.segment_of(subject)
        if segment_key not in benchmarks:
            existing = db.scalar(select(MarketBenchmark).where(MarketBenchmark.job_id == self.job_id, MarketBenchmark.segment_key == segment_key))
            if existing is None:
                existing = MarketBenchmark(job_id=self.job_id, **analyzer.benchmark(subject, filters.market_window_days))
                db.add(existing)
                db.flush()
            benchmarks[segment_key] = existing.id

        db.execute(update(OpportunityScore).where(OpportunityScore.listing_id == listing.id, OpportunityScore.is_latest.is_(True)).values(is_latest=False))
        score = OpportunityScore(
            job_id=self.job_id, listing_id=listing.id, is_latest=True, is_opportunity=eligible, is_suspicious=risk.suspicious,
            score=total, classification=scorer.classify(total), price_advantage_score=price_score, nlp_score=analysis.score,
            freshness_score=fresh_score, discount_pct=discount, reference_kind=comparables.kind, reference_value=reference_value,
            market_median_price=market_median, market_avg_price=market_avg, estimated_gap=gap,
            comparable_count=comparables.stats.count if comparables.stats else 0, comparable_level=comparables.level_label,
            comparable_ids=[o.id for o in comparables.items][:200], segment_key=segment_key, gross_yield_pct=gross_yield,
            confidence=confidence, confidence_label=scorer.confidence_label(confidence), risk_score=risk.score,
            risk_level=risk.level, reliability=scorer.reliability_score(listing.data_quality, confidence),
            warnings=warnings, nlp={**analysis.as_dict(), "ineligible_reason": reason}, signal_keys="," + ",".join(sorted(keys)) + ",",
        )
        db.add(score)
        db.flush()
        age = (self.today - listing.listed_at).days if listing.listed_at else None
        report = build_report(listing, comparables, analysis, discount, gap, age, gross_yield, risk.warnings, score.confidence_label)
        db.add(OpportunityReport(score_id=score.id, summary=report["summary"], details=report["details"]))
        return score

    # --- 4. sıralama -------------------------------------------------------------------------

    def _stage_rank(self, filters: ListingFilters, settings: AppSettings) -> None:
        with session_scope() as db:
            scores = list(db.scalars(select(OpportunityScore).where(OpportunityScore.job_id == self.job_id)))
            scores.sort(key=lambda s: (s.is_opportunity, s.score, s.discount_pct or 0, s.confidence), reverse=True)
            for rank, score in enumerate(scores, start=1):
                score.rank = rank
            job = db.get(AgentJob, self.job_id)
            job.opportunities = sum(1 for s in scores if s.is_opportunity)
            db.commit()
            minimum = settings.agent.min_opportunities
            if job.opportunities < minimum:
                self._log(
                    db,
                    f"Kriterleri karşılayan {job.opportunities} fırsat bulundu (hedef {minimum}). "
                    "Sayıyı doldurmak için düşük kaliteli ilan eklenmedi.",
                    "warning",
                )
            self._progress(db, "rank", 1, 1)


class JobControl:
    def __init__(self) -> None:
        self.pause = threading.Event()
        self.stop = threading.Event()


class AgentManager:
    """Görevleri sırayla tek arka plan iş parçacığında çalıştırır."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._current: Optional[str] = None
        self._control = JobControl()
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()

    def start_worker(self) -> None:
        with session_scope() as db:
            db.execute(update(AgentJob).where(AgentJob.status.in_(("running", "pausing", "stopping"))).values(status="interrupted", last_action="Sunucu yeniden başladı; görev devam ettirilebilir."))
            db.commit()
        self._thread = threading.Thread(target=self._loop, name="hky-agent", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._shutdown.set()
        self._control.pause.set()
        self._wake.set()

    def _next_job(self) -> Optional[str]:
        with session_scope() as db:
            return db.scalar(select(AgentJob.id).where(AgentJob.status == "queued").order_by(AgentJob.created_at).limit(1))

    def _loop(self) -> None:
        while not self._shutdown.is_set():
            job_id = self._next_job()
            if job_id is None:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            with self._lock:
                self._current, self._control = job_id, JobControl()
            AgentRunner(job_id, self._control).run()
            with self._lock:
                self._current = None

    def create_job(self, db: Session, user_id: int, filters: ListingFilters, source_keys: List[str], profile_id: Optional[int], profile_name: str) -> AgentJob:
        job = AgentJob(
            id=str(uuid.uuid4()), profile_id=profile_id, profile_name=profile_name, filters=filters.model_dump(mode="json"),
            settings_snapshot=load_settings(db).model_dump(), source_keys=source_keys, created_by=user_id,
        )
        db.add(job)
        db.commit()
        self._wake.set()
        return job

    def pause(self, db: Session, job: AgentJob) -> None:
        with self._lock:
            if job.id == self._current:
                job.status = "pausing"
                self._control.pause.set()
            elif job.status == "queued":
                job.status = "paused"
        db.commit()

    def resume(self, db: Session, job: AgentJob) -> None:
        job.status = "queued"
        db.commit()
        self._wake.set()

    def stop(self, db: Session, job: AgentJob) -> None:
        with self._lock:
            if job.id == self._current:
                job.status = "stopping"
                self._control.stop.set()
            else:
                job.status, job.finished_at = "stopped", utcnow()
        db.commit()


manager = AgentManager()
