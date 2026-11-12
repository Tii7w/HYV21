"""Agent Control Center uç noktaları; görev yönetimi yalnızca yöneticiye açıktır."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agent.runner import job_payload, manager
from ..db import get_db
from ..models import AgentJob, AgentJobItem, AgentJobLog, DataSource, DeadLetter, User, utcnow
from ..providers.base import STATE_ACCESS_DENIED, STATE_OK
from ..providers.registry import build_provider
from ..providers.sahibinden import cooldown_message
from ..schemas import JobCreate, ListingFilters
from ..security import current_user, require_admin
from .profiles import owned_profile

router = APIRouter(prefix="/api/agent", tags=["agent"])

TRANSITIONS = {
    "pause": ("queued", "running"),
    "resume": ("paused", "interrupted"),
    "stop": ("queued", "running", "paused", "pausing", "interrupted"),
}


def _job(db: Session, job_id: str) -> AgentJob:
    job = db.get(AgentJob, job_id)
    if job is None:
        raise HTTPException(404, "Görev bulunamadı.")
    return job


def _detail(db: Session, job: AgentJob) -> dict:
    counts = {
        f"{kind}_{status}": count
        for kind, status, count in db.execute(
            select(AgentJobItem.kind, AgentJobItem.status, func.count()).where(AgentJobItem.job_id == job.id).group_by(AgentJobItem.kind, AgentJobItem.status)
        )
    }
    dead_letters = db.scalar(select(func.count(DeadLetter.id)).where(DeadLetter.job_id == job.id))
    return {**job_payload(job), "queue": counts, "dead_letters": dead_letters}


def _validate_sources(db: Session, keys: List[str], filters: ListingFilters) -> None:
    sources = {s.key: s for s in db.scalars(select(DataSource).where(DataSource.key.in_(keys)))}
    for key in keys:
        source = sources.get(key)
        if source is None:
            raise HTTPException(422, f"Bilinmeyen veri kaynağı: {key}")
        if not source.enabled:
            raise HTTPException(422, f"{source.name} devre dışı. Tarama Ayarları'ndan etkinleştirin.")
        if source.status == STATE_ACCESS_DENIED:
            raise HTTPException(422, f"{source.name} için erişim reddedilmişti. Yetkili erişimi doğrulayıp bağlantıyı yeniden test edin.")
        if key == "authorized":
            config = source.config or {}
            if not config.get("base_url") or not config.get("authorized_use"):
                raise HTTPException(422, f"{source.name}: besleme adresi ve yetkili kullanım onayı gerekli.")
        elif key in ("sahibinden", "manual_import"):
            waiting = cooldown_message(source, utcnow())
            if waiting:
                raise HTTPException(422, waiting)
            check = build_provider(source, lambda: None).check()
            if check.state != STATE_OK:
                raise HTTPException(422, f"{source.name}: {check.message}")
    is_demo_job = filters.data_mode == "demo"
    if is_demo_job != ("demo" in keys) or (is_demo_job and len(keys) > 1):
        raise HTTPException(422, "DEMO kaynağı yalnızca DEMO veri moduyla ve tek başına çalıştırılabilir.")


@router.get("/jobs")
def list_jobs(limit: int = Query(default=30, ge=1, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)) -> List[dict]:
    jobs = db.scalars(select(AgentJob).order_by(AgentJob.created_at.desc()).limit(limit))
    return [job_payload(job) for job in jobs]


@router.post("/jobs", status_code=201)
def create_job(body: JobCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    keys = list(dict.fromkeys(body.source_keys))
    _validate_sources(db, keys, body.filters)
    name = "Anlık filtre"
    if body.profile_id is not None:
        profile = owned_profile(db, body.profile_id, user)
        profile.last_run_at, name = utcnow(), profile.name
    job = manager.create_job(db, user.id, body.filters, keys, body.profile_id, name)
    return _detail(db, job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _detail(db, _job(db, job_id))


@router.get("/jobs/{job_id}/logs")
def job_logs(job_id: str, after_id: Optional[int] = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> List[dict]:
    stmt = select(AgentJobLog).where(AgentJobLog.job_id == _job(db, job_id).id, AgentJobLog.level != "debug")
    if after_id:
        stmt = stmt.where(AgentJobLog.id > after_id)
    logs = db.scalars(stmt.order_by(AgentJobLog.id.desc()).limit(300))
    return [{"id": log.id, "at": log.at.isoformat() + "Z", "level": log.level, "message": log.message} for log in reversed(list(logs))]


@router.get("/jobs/{job_id}/dead-letters")
def job_dead_letters(job_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> List[dict]:
    rows = db.scalars(select(DeadLetter).where(DeadLetter.job_id == _job(db, job_id).id).order_by(DeadLetter.id.desc()).limit(200))
    return [
        {"id": r.id, "source_key": r.source_key, "url": r.url, "status_code": r.status_code, "error": r.error, "attempts": r.attempts, "created_at": r.created_at.isoformat() + "Z"}
        for r in rows
    ]


@router.post("/jobs/{job_id}/{action}")
def control_job(job_id: str, action: str, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    job = _job(db, job_id)
    if action == "restart":
        filters = ListingFilters.model_validate(job.filters)
        _validate_sources(db, job.source_keys, filters)
        new_job = manager.create_job(db, user.id, filters, job.source_keys, job.profile_id, job.profile_name)
        return _detail(db, new_job)
    if action not in TRANSITIONS:
        raise HTTPException(404, "Bilinmeyen işlem.")
    if job.status not in TRANSITIONS[action]:
        raise HTTPException(409, f"'{job.status}' durumundaki görev için bu işlem yapılamaz.")
    getattr(manager, action)(db, job)
    return _detail(db, job)
