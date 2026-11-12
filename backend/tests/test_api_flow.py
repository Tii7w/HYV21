import time
import uuid

from sqlalchemy import func, select

from app.agent.runner import AgentRunner, JobControl
from app.db import SessionLocal
from app.models import AgentJob, AgentJobItem, Listing, ListingPriceHistory, ListingSnapshot, Notification, OpportunityScore, User
from app.schemas import AppSettings, ListingFilters
from app.security import hash_password

SCENARIO = {
    "data_mode": "demo", "main_category": "emlak", "categories": ["satilik-konut"], "cities": ["Bursa"],
    "districts": ["Nilüfer"], "market_window_days": 30, "opportunity_window_days": 14, "min_score": 80,
}


def wait_for(client, job_id, statuses=("completed", "failed", "stopped"), timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/agent/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.3)
    raise AssertionError(f"Görev bitmedi: {job}")


def enable_demo(client):
    assert client.put("/api/sources/demo", json={"enabled": True}).status_code == 200


def test_auth_and_csrf(app_client):
    assert app_client.get("/api/opportunities").status_code == 401
    assert app_client.post("/api/auth/login", json={"email": "admin@test.local", "password": "yanlis"}).status_code == 401
    app_client.post("/api/auth/login", json={"email": "admin@test.local", "password": "test-pass-123"})
    # Özel başlık olmadan değiştiren istek reddedilir.
    assert app_client.post("/api/profiles", json={"name": "x", "filters": {}}).status_code == 403


def test_viewer_cannot_manage(app_client):
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == "viewer@test.local")):
            db.add(User(email="viewer@test.local", password_hash=hash_password("viewer-pass-1"), role="viewer"))
            db.commit()
    app_client.post("/api/auth/login", json={"email": "viewer@test.local", "password": "viewer-pass-1"})
    headers = {"X-HKY-CSRF": "1"}
    assert app_client.get("/api/settings").status_code == 403
    assert app_client.post("/api/agent/jobs", json={"filters": {}, "source_keys": ["demo"]}, headers=headers).status_code == 403
    assert app_client.get("/api/opportunities").status_code == 200


def test_location_hierarchy_and_catalog(admin):
    response = admin.post("/api/listings/search", json={"filters": {"districts": ["Nilüfer"]}})
    assert response.status_code == 422
    assert "İlçe seçmek için" in response.text
    hoods = admin.get("/api/catalog/neighbourhoods", params={"city": "Bursa", "district": ["Nilüfer"]}).json()
    assert "Ataevler" in hoods["Nilüfer"]


def test_sahibinden_job_refused_honestly(admin, monkeypatch):
    """Scraper paketleri yoksa iş başlatılmaz, eksik paket adıyla reddedilir."""
    from app.providers import sahibinden

    monkeypatch.setattr(sahibinden, "missing_packages", lambda: ["scrapling", "patchright"])
    admin.put("/api/sources/sahibinden", json={"enabled": True})
    response = admin.post("/api/agent/jobs", json={"filters": {}, "source_keys": ["sahibinden"]})
    assert response.status_code == 422
    assert "Scraper paketleri kurulu değil: scrapling, patchright" in response.text


def test_demo_cannot_mix_with_real(admin):
    enable_demo(admin)
    response = admin.post("/api/agent/jobs", json={"filters": {"data_mode": "real"}, "source_keys": ["demo"]})
    assert response.status_code == 422


def test_bursa_nilufer_scenario_and_notifications(admin):
    enable_demo(admin)
    created = admin.post("/api/agent/jobs", json={"filters": SCENARIO, "source_keys": ["demo"]})
    assert created.status_code == 201, created.text
    job = wait_for(admin, created.json()["id"])
    assert job["status"] == "completed", job
    assert job["opportunities"] >= 3

    found = admin.post("/api/listings/search", json={"filters": {**SCENARIO, "only_opportunities": True}, "sort": "score"}).json()
    scores = [item["score"]["score"] for item in found["items"]]
    assert len(scores) >= 3 and all(s >= 80 for s in scores) and scores == sorted(scores, reverse=True)
    for item in found["items"]:
        listing = item["listing"]
        assert listing["is_demo"] and listing["city"] == "Bursa" and listing["district"] == "Nilüfer"
        assert item["score"]["comparable_count"] >= 5 and item["score"]["summary"]

    # Aynı oran kartta ve özet metninde aynı yazılır (tek yerde yuvarlanır).
    first = found["items"][0]["score"]
    assert f"%{first['discount_pct']:.1f}".replace(".", ",") in first["summary"]

    detail = admin.get(f"/api/opportunities/{found['items'][0]['score']['id']}").json()
    assert detail["comparables"] and detail["benchmark"]["sample_size"] > 0 and detail["disclaimer"]
    assert "emsal" in detail["report"]["summary"]

    # Şüpheli derecede ucuz ilanlar fırsat listesine girmez.
    with SessionLocal() as db:
        assert not db.scalar(select(func.count(OpportunityScore.id)).where(OpportunityScore.is_opportunity.is_(True), OpportunityScore.is_suspicious.is_(True)))

    notes = admin.get("/api/notifications").json()
    assert notes["unread"] >= 1 and all(n["score"] > 80 and n["is_demo"] for n in notes["items"])
    first_count = len(notes["items"])

    again = admin.post(f"/api/agent/jobs/{job['id']}/restart").json()
    assert wait_for(admin, again["id"])["status"] == "completed"
    assert len(admin.get("/api/notifications").json()["items"]) == first_count  # Tekrar bildirim engellendi.

    real = admin.get("/api/opportunities", params={"data_mode": "real"}).json()
    assert real["items"] == []  # DEMO sonuçları gerçek veri gibi gösterilmez.

    # "Bulunan fırsatlar" sekmesi: her ilan bir kez, iki taramada da bulunduğu için times_found >= 2.
    saved = admin.get("/api/opportunities/found", params={"data_mode": "demo"}).json()
    assert saved["total"] >= 3 and len(saved["items"]) == saved["total"]
    assert len({item["listing"]["id"] for item in saved["items"]}) == saved["total"]
    for item in saved["items"]:
        assert item["score"]["is_opportunity"] and item["listing"]["is_demo"]
        assert item["times_found"] >= 2 and item["still_opportunity"]
        assert item["first_found_at"] <= item["last_found_at"]
    assert admin.get("/api/opportunities/found", params={"data_mode": "real"}).json()["total"] == 0
    paged = admin.get("/api/opportunities/found", params={"data_mode": "demo", "page_size": 1}).json()
    assert len(paged["items"]) == 1 and paged["total"] == saved["total"]


def test_pause_and_resume_do_not_reprocess(admin):
    enable_demo(admin)
    filters = ListingFilters.model_validate({**SCENARIO, "min_score": None})
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.role == "admin"))
        job = AgentJob(id=str(uuid.uuid4()), filters=filters.model_dump(mode="json"), settings_snapshot=AppSettings().model_dump(),
                       source_keys=["demo"], created_by=user_id, status="paused")
        db.add(job)
        db.commit()
        job_id = job.id

    control = JobControl()
    runner = AgentRunner(job_id, control)
    original_checkpoint, calls = runner._checkpoint, [0]

    def pause_midway():
        calls[0] += 1
        if calls[0] == 60:
            control.pause.set()
        original_checkpoint()

    runner._checkpoint = pause_midway
    runner.run()
    with SessionLocal() as db:
        assert db.get(AgentJob, job_id).status == "paused"
        done_before = db.scalar(select(func.count(AgentJobItem.id)).where(AgentJobItem.job_id == job_id, AgentJobItem.status == "done"))
        assert done_before > 0

    AgentRunner(job_id, JobControl()).run()
    with SessionLocal() as db:
        assert db.get(AgentJob, job_id).status == "completed"
        per_listing = db.execute(
            select(ListingSnapshot.listing_id, func.count()).where(ListingSnapshot.job_id == job_id).group_by(ListingSnapshot.listing_id)
        ).all()
        assert per_listing and max(count for _, count in per_listing) == 1
        items = db.scalar(select(func.count(AgentJobItem.id)).where(AgentJobItem.job_id == job_id, AgentJobItem.kind == "score"))
        scores = db.scalar(select(func.count(OpportunityScore.id)).where(OpportunityScore.job_id == job_id))
        assert items == scores


def test_import_price_change_history(admin):
    csv_v1 = "İlan No;Kategori;İl;İlçe;Mahalle;Fiyat;m² (Brüt);Oda Sayısı;İlan Tarihi;Telefon\nIMP-1;Satılık Daire;İzmir;Karşıyaka;Bostanlı;6.000.000 TL;110;3+1;Bugün;0532\n"
    upload = admin.post("/api/imports", data={"authorized": "true"}, files={"file": ("liste.csv", csv_v1.encode("utf-8"), "text/csv")})
    assert upload.status_code == 201 and upload.json()["dropped_columns"] == ["Telefon"]
    job = admin.post("/api/agent/jobs", json={"filters": {}, "source_keys": ["manual_import"]}).json()
    assert wait_for(admin, job["id"])["status"] == "completed"

    csv_v2 = csv_v1.replace("6.000.000", "5.400.000")
    admin.post("/api/imports", data={"authorized": "true"}, files={"file": ("liste2.csv", csv_v2.encode("utf-8"), "text/csv")})
    job = admin.post("/api/agent/jobs", json={"filters": {}, "source_keys": ["manual_import"]}).json()
    assert wait_for(admin, job["id"])["status"] == "completed"

    with SessionLocal() as db:
        listing = db.scalar(select(Listing).where(Listing.source_listing_id == "IMP-1"))
        prices = [h.price for h in db.scalars(select(ListingPriceHistory).where(ListingPriceHistory.listing_id == listing.id).order_by(ListingPriceHistory.id))]
        count = db.scalar(select(func.count(Listing.id)).where(Listing.source_listing_id == "IMP-1"))
    assert count == 1 and prices == [6_000_000, 5_400_000] and listing.price_drop_pct == 10.0


def test_near_duplicates_need_same_size():
    from app.agent.ingest import mark_near_duplicates
    from app.models import ListingDescription

    text = "Merkezi konumda, bakımlı, otoparklı, asansörlü site içinde daire"
    with SessionLocal() as db:
        rows = []
        for source_id, m2 in (("ND-1", 120), ("ND-2", 120), ("ND-3", 150)):
            listing = Listing(source_key="manual_import", source_listing_id=source_id, main_category="emlak", category="satilik-konut",
                              property_type="Daire", title="Ataşehir 3+1 Daire", city="İstanbul", district="Ataşehir",
                              neighbourhood="Barbaros", rooms="3+1", m2_gross=m2, price=9_000_000)
            db.add(listing)
            db.flush()
            db.add(ListingDescription(listing_id=listing.id, text=text, text_hash=source_id))
            rows.append(listing)
        db.commit()
        assert mark_near_duplicates(db, [r.id for r in rows]) == 1
        db.expire_all()
        assert db.get(Listing, rows[1].id).duplicate_of_id == rows[0].id
        assert db.get(Listing, rows[2].id).duplicate_of_id is None  # Farklı m²: aynı binada başka daire.


def test_import_requires_attestation(admin):
    response = admin.post("/api/imports", data={"authorized": "false"}, files={"file": ("x.csv", b"a;b\n1;2\n", "text/csv")})
    assert response.status_code == 422


def test_profiles_crud(admin):
    created = admin.post("/api/profiles", json={"name": "Bursa Nilüfer Satılık Daire", "filters": SCENARIO})
    assert created.status_code == 201
    assert admin.post("/api/profiles", json={"name": "Bursa Nilüfer Satılık Daire", "filters": {}}).status_code == 409
    profile_id = created.json()["id"]
    assert admin.get("/api/profiles").json()[0]["filters"]["districts"] == ["Nilüfer"]
    assert admin.delete(f"/api/profiles/{profile_id}").status_code == 200


def test_secrets_never_returned(admin):
    admin.put("/api/sources/authorized", json={"base_url": "https://feed.example.com/items", "api_key": "SUPER-SECRET", "authorized_use": True})
    body = admin.get("/api/sources").text
    assert "SUPER-SECRET" not in body and '"api_key_set":true' in body.replace(" ", "")
    settings = admin.get("/api/settings").json()
    settings["proxy"] = {**settings["proxy"], "enabled": True, "host": "proxy.local", "port": 8080, "authorized_use": True}
    settings["proxy_password"] = "PROXY-PASS"
    saved = admin.put("/api/settings", json={k: v for k, v in settings.items() if k != "proxy_password_set"})
    assert saved.status_code == 200 and "PROXY-PASS" not in saved.text and saved.json()["proxy_password_set"]
    blocked = admin.put("/api/sources/authorized", json={"base_url": "https://www.sahibinden.com/api"})
    assert blocked.status_code == 422


# --- Filtrelerin taramaya bağlanması ve gerçek veri modu --------------------------------------

def test_unmet_opportunity_flags():
    from app.filters import unmet_opportunity_flags

    f = ListingFilters(urgent=True, bargain=True, price_dropped=True, below_regional_median=True)
    assert unmet_opportunity_flags(f, {"urgent", "bargain"}, 900, 1000, 950, 5.0) == []
    assert unmet_opportunity_flags(f, {"urgent"}, 900, 1000, 950, 5.0) == ["Kelepir"]
    unmet = unmet_opportunity_flags(f, set(), 1000, None, None, None)
    assert unmet == ["Acil satılık", "Kelepir", "Fiyatı düşen", "Bölge medyanının altında"]
    # Hiç kutu seçilmemişse hiçbir şey zorunlu değildir.
    assert unmet_opportunity_flags(ListingFilters(), set(), 1000, None, None, None) == []


def test_seller_filter_applies_to_emlak():
    from app.filters import apply_listing_filters

    with SessionLocal() as db:
        for source_id, seller in (("SELLER-1", "Sahibinden"), ("SELLER-2", "Emlak Ofisinden")):
            db.add(Listing(source_key="manual_import", source_listing_id=source_id, main_category="emlak", category="satilik-konut",
                           title="Test daire", city="Eskişehir", district="Odunpazarı", price=3_000_000, seller_type=seller))
        db.commit()
        f = ListingFilters(main_category="emlak", cities=["Eskişehir"], seller_types=["Sahibinden"], opportunity_window_days=None)
        ids = list(db.scalars(apply_listing_filters(select(Listing.source_listing_id), f)))
    assert ids == ["SELLER-1"]


def test_sources_report_readiness(admin, monkeypatch):
    from app.api import settings as settings_api

    monkeypatch.setattr(settings_api, "sahibinden_missing_packages", lambda: ["scrapling"])
    sources = {s["key"]: s for s in admin.get("/api/sources").json()}
    assert sources["sahibinden"]["ready"] is False and "scrapling" in sources["sahibinden"]["ready_message"]
    assert sources["demo"]["ready"] is True


def _real_import_csv() -> bytes:
    """DEMO üreticisinin satırlarını 'kullanıcının yüklediği gerçek dosya' gibi CSV'ye çevirir."""
    import csv
    import io
    import random
    from datetime import date

    from app.providers.demo import _housing

    rows = [r for r in _housing(date.today(), random.Random("real-mode")) if r["İl"] == "Bursa"]
    for row in rows:
        row["İlan No"] = row["İlan No"].replace("DEMO-", "REAL-")
        row["İlan Başlığı"] = row["İlan Başlığı"].replace("[DEMO] ", "")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def test_real_mode_agent_works_like_demo(admin):
    """Gerçek veri modunda (dosyadan gelen ilanlar) agent, DEMO ile aynı uçtan uca akışı çalıştırır."""
    upload = admin.post("/api/imports", data={"authorized": "true"}, files={"file": ("bursa.csv", _real_import_csv(), "text/csv")})
    assert upload.status_code == 201, upload.text
    sources = {s["key"]: s for s in admin.get("/api/sources").json()}
    assert sources["manual_import"]["ready"] is True

    real_filters = {"data_mode": "real", "main_category": "emlak", "categories": ["satilik-konut"], "cities": ["Bursa"], "districts": ["Nilüfer"]}
    created = admin.post("/api/agent/jobs", json={"filters": real_filters, "source_keys": ["manual_import"]})
    assert created.status_code == 201, created.text
    job = wait_for(admin, created.json()["id"])
    assert job["status"] == "completed" and job["opportunities"] >= 3, job

    saved = admin.get("/api/opportunities/found", params={"data_mode": "real"}).json()
    real_items = [i for i in saved["items"] if i["listing"]["source_listing_id"].startswith("REAL-")]
    assert len(real_items) >= 3
    assert all(not i["listing"]["is_demo"] and i["listing"]["city"] == "Bursa" and i["listing"]["district"] == "Nilüfer" for i in real_items)

    # Seçili fırsat kutusu taramada zorunludur: "Acil satılık" ile yalnızca acil ilanlar fırsat sayılır.
    urgent_job = admin.post("/api/agent/jobs", json={"filters": {**real_filters, "urgent": True}, "source_keys": ["manual_import"]}).json()
    urgent_job = wait_for(admin, urgent_job["id"])
    assert urgent_job["status"] == "completed"
    with SessionLocal() as db:
        urgent_scores = list(db.scalars(select(OpportunityScore).where(OpportunityScore.job_id == urgent_job["id"])))
    opportunities = [s for s in urgent_scores if s.is_opportunity]
    assert opportunities and all(",urgent," in s.signal_keys for s in opportunities)
    skipped = [s for s in urgent_scores if not s.is_opportunity and "Acil satılık" in (s.nlp.get("ineligible_reason") or "")]
    assert urgent_job["opportunities"] == len(opportunities) < job["opportunities"]
    assert skipped, "acil olmayan fırsatlar 'Acil satılık' kutusu yüzünden elenmeliydi"


def test_sahibinden_block_fails_job_and_starts_cooldown(admin, monkeypatch):
    """Engel sayfası gelince görev 'tamamlandı, 0 fırsat' değil hata ile biter ve kimlik dinlenmeye alınır."""
    from app.api import settings as settings_api
    from app.providers import sahibinden
    from app.services.scraper.sahibinden_scraper import NotAListingPage

    def blocked(url):
        raise NotAListingPage("doğrulama sayfası")

    monkeypatch.setattr(sahibinden, "missing_packages", lambda: [])
    monkeypatch.setattr(settings_api, "sahibinden_missing_packages", lambda: [])
    monkeypatch.setattr(sahibinden, "fetch_page", blocked)
    admin.put("/api/sources/sahibinden", json={"enabled": True})

    # Veritabanındaki önceki gerçek kayıtlara uymayan filtre: analiz edilecek ilan kalmaz.
    nothing = {"data_mode": "real", "price_min": 10**12}
    created = admin.post("/api/agent/jobs", json={"filters": nothing, "source_keys": ["sahibinden"]})
    assert created.status_code == 201, created.text
    job = wait_for(admin, created.json()["id"])
    assert job["status"] == "failed", job
    assert "ilan alınamadığı" in job["error"] and "erişimi engelledi" in job["error"]

    source = {s["key"]: s for s in admin.get("/api/sources").json()}["sahibinden"]
    assert source["name"] == "Sahibinden.com (web sayfası)"
    assert source["ready"] is False and "dk" in source["ready_message"]

    # Bekleme süresinde yeni tarama, yeniden başlatma ve bağlantı testi engeli silmez.
    again = admin.post("/api/agent/jobs", json={"filters": {"data_mode": "real"}, "source_keys": ["sahibinden"]})
    assert again.status_code == 422 and "dinlenmede" in again.text
    assert admin.post(f"/api/agent/jobs/{job['id']}/restart").status_code == 422
    admin.post("/api/sources/sahibinden/test")
    assert {s["key"]: s for s in admin.get("/api/sources").json()}["sahibinden"]["ready"] is False


def test_cooldown_expires():
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from app.providers.sahibinden import BLOCK_COOLDOWN, BLOCK_MARKER, cooldown_message

    now = datetime(2026, 1, 1, 12, 0)
    source = SimpleNamespace(key="sahibinden", status_message=f"{BLOCK_MARKER}: x", last_checked_at=now - timedelta(minutes=5))
    assert "26 dk" in cooldown_message(source, now)
    source.last_checked_at = now - BLOCK_COOLDOWN
    assert cooldown_message(source, now) is None
    other = SimpleNamespace(key="sahibinden", status_message="Scraper paketleri hazır.", last_checked_at=now)
    assert cooldown_message(other, now) is None
