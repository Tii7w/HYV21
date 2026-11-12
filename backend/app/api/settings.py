"""Tarama ayarları, veri kaynakları, proxy testi ve dosya içe aktarma."""

from typing import List, Tuple
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DataSource, ImportBatch, User, utcnow
from ..network.client import BlockedHostError, is_blocked_host
from ..providers.base import STATE_ACCESS_DENIED, STATE_ERROR, STATE_OK
from ..providers.listing_links import import_listing_links
from ..providers.manual_import import ImportError_, parse_import_file
from ..providers.registry import build_client_factory, build_provider, build_proxy
from ..providers.sahibinden import cooldown_message
from ..providers.sahibinden import missing_packages as sahibinden_missing_packages
from ..schemas import ListingLinksImport, SettingsUpdate, SourceUpdate
from ..security import current_user, encrypt_secret, redact, require_admin
from ..settings_store import load_settings, load_settings_row, proxy_password

router = APIRouter(prefix="/api", tags=["settings"])
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
PROXY_TEST_URL = "https://www.google.com/generate_204"


def _settings_dict(db: Session) -> dict:
    row = load_settings_row(db)
    return {**load_settings(db).model_dump(), "proxy_password_set": bool(row.proxy_password_encrypted)}


def _source_dict(source: DataSource) -> dict:
    config = source.config or {}
    return {
        "key": source.key, "name": source.name, "kind": source.kind, "enabled": source.enabled, "status": source.status,
        "status_message": source.status_message,
        "last_checked_at": source.last_checked_at.isoformat() + "Z" if source.last_checked_at else None,
        "config": {k: config.get(k) for k in ("base_url", "results_path", "next_cursor_path", "cursor_param", "auth_header", "auth_prefix", "authorized_use")},
        "api_key_set": bool(source.secret_encrypted),
    }


@router.get("/settings")
def get_settings_(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    return _settings_dict(db)


@router.get("/settings/public")
def public_settings(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Arayüzün bildirim davranışı için gereken, gizli olmayan ayarlar."""
    settings = load_settings(db)
    return {"notifications": settings.notifications.model_dump(), "agent": settings.agent.model_dump()}


@router.put("/settings")
def update_settings(body: SettingsUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    row = load_settings_row(db)
    row.data = body.model_dump(exclude={"proxy_password"})
    if body.proxy_password is not None:
        row.proxy_password_encrypted = encrypt_secret(body.proxy_password) if body.proxy_password else None
    db.commit()
    return _settings_dict(db)


@router.post("/settings/proxy/test")
def test_proxy(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    settings = load_settings(db)
    proxy = build_proxy(settings, proxy_password(db))
    if proxy is None:
        raise HTTPException(422, "Önce proxy bilgilerini kaydedip izinli kullanım onayıyla etkinleştirin.")
    try:
        with httpx.Client(proxy=proxy.url(), timeout=settings.scan.timeout_seconds) as client:
            response = client.get(PROXY_TEST_URL)
        return {"ok": response.status_code < 400, "message": f"Proxy yanıt verdi (HTTP {response.status_code})."}
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"Proxy bağlantısı başarısız: {redact(exc)}"}


def _readiness(source: DataSource, db: Session) -> Tuple[bool, str]:
    """Kaynak şu an bir tarama başlatabilir mi? Ağa çıkmayan, ucuz kontrollerdir."""
    if source.key == "manual_import":
        batches = db.scalar(select(func.count(ImportBatch.id))) or 0
        return (True, "") if batches else (False, "Henüz dosya yüklenmedi (Tarama ayarları → Dosya içe aktarma).")
    if source.key == "sahibinden":
        missing = sahibinden_missing_packages()
        if missing:
            return False, f"Scraper paketleri kurulu değil: {', '.join(missing)}"
        waiting = cooldown_message(source, utcnow())
        return (False, waiting) if waiting else (True, "")
    if source.key == "authorized":
        config = source.config or {}
        ok = bool(config.get("base_url") and config.get("authorized_use"))
        return (True, "") if ok else (False, "Besleme adresi ve yetkili kullanım onayı gerekli.")
    return True, ""


@router.get("/sources")
def list_sources(user: User = Depends(current_user), db: Session = Depends(get_db)) -> List[dict]:
    items = []
    for source in db.scalars(select(DataSource).order_by(DataSource.id)):
        ready, message = _readiness(source, db)
        items.append({**_source_dict(source), "ready": ready, "ready_message": message})
    return items


@router.put("/sources/{key}")
def update_source(key: str, body: SourceUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    source = db.scalar(select(DataSource).where(DataSource.key == key))
    if source is None:
        raise HTTPException(404, "Kaynak bulunamadı.")
    config = dict(source.config or {})
    changes = body.model_dump(exclude_unset=True, exclude={"enabled", "api_key"})
    if "base_url" in changes and changes["base_url"]:
        parts = urlsplit(changes["base_url"])
        if parts.scheme != "https" or not parts.netloc:
            raise HTTPException(422, "Besleme adresi https:// ile başlayan geçerli bir adres olmalıdır.")
        if is_blocked_host(changes["base_url"]):
            raise HTTPException(422, "Sahibinden adresleri yalnızca resmi API sözleşmesiyle eklenebilir.")
    config.update(changes)
    source.config = config
    if body.api_key is not None:
        source.secret_encrypted = encrypt_secret(body.api_key) if body.api_key else None
    if body.enabled is not None:
        source.enabled = body.enabled
    if changes or body.api_key is not None:
        # Yapılandırma değişince önceki 'erişim reddedildi' durumu ancak yeni testle kalkar.
        source.status_message = "Ayarlar değişti; bağlantıyı test edin."
    db.commit()
    return _source_dict(source)


@router.post("/sources/{key}/test")
def test_source(key: str, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    source = db.scalar(select(DataSource).where(DataSource.key == key))
    if source is None:
        raise HTTPException(404, "Kaynak bulunamadı.")
    if cooldown_message(source, utcnow()):
        # Paket kontrolü engel kaydını silmesin; bekleme süresi dolana kadar durum korunur.
        return _source_dict(source)
    factory = build_client_factory(source, load_settings(db), proxy_password(db))
    try:
        check = build_provider(source, factory).check()
    except BlockedHostError as exc:
        check_state, check_message = "error", str(exc)
    else:
        check_state, check_message = check.state, check.message
    source.status, source.status_message, source.last_checked_at = check_state, redact(check_message)[:500], utcnow()
    db.commit()
    return _source_dict(source)


@router.get("/imports")
def list_imports(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> List[dict]:
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()))
    return [
        {"id": b.id, "filename": b.filename, "row_count": b.row_count, "dropped_columns": b.dropped_columns, "created_at": b.created_at.isoformat() + "Z"}
        for b in batches
    ]


@router.post("/imports", status_code=201)
async def upload_import(
    file: UploadFile = File(...),
    authorized: bool = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if not authorized:
        raise HTTPException(422, "Dosyadaki verileri kullanma yetkiniz olduğunu onaylamanız gerekiyor.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Dosya 15 MB sınırını aşıyor.")
    filename = (file.filename or "dosya").replace("\\", "/").split("/")[-1][:255]
    try:
        rows, dropped = parse_import_file(filename, content)
    except ImportError_ as exc:
        raise HTTPException(422, str(exc))
    batch = ImportBatch(filename=filename, rows=rows, row_count=len(rows), dropped_columns=dropped, attested_by=user.id)
    db.add(batch)
    source = db.scalar(select(DataSource).where(DataSource.key == "manual_import"))
    source.status, source.status_message, source.last_checked_at = STATE_OK, f"Son yükleme: {filename} ({len(rows)} satır)", utcnow()
    db.commit()
    return {"id": batch.id, "filename": filename, "row_count": len(rows), "dropped_columns": dropped}


@router.post("/imports/links", status_code=201)
def upload_listing_links(
    body: ListingLinksImport,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if not body.authorized:
        raise HTTPException(422, "Bağlantılardaki verileri kullanma ve otomatik erişim yetkiniz olduğunu onaylamanız gerekiyor.")
    if any(len(url) > 2048 for url in body.urls):
        raise HTTPException(422, "Bağlantı en fazla 2048 karakter olabilir.")
    if len(set(body.urls)) != len(body.urls):
        raise HTTPException(422, "Aynı bağlantı birden fazla kez eklenemez.")

    try:
        rows, results = import_listing_links(body.urls)
    except PlaywrightError as exc:
        raise HTTPException(
            503,
            f"Playwright Chromium başlatılamadı. Backend ortamında 'python -m playwright install chromium' çalıştırın. Ayrıntı: {exc}",
        ) from exc

    source = db.scalar(select(DataSource).where(DataSource.key == "manual_import"))
    if source is None:
        raise HTTPException(500, "Dosya içe aktarma kaynağı yapılandırılmamış.")

    batch = None
    if rows:
        batch = ImportBatch(
            filename=f"Bağlantı içe aktarma ({len(rows)} ilan)",
            rows=rows,
            row_count=len(rows),
            dropped_columns=[],
            attested_by=user.id,
        )
        db.add(batch)
        skipped = len(results) - len(rows)
        source.status = STATE_OK
        source.status_message = f"{len(rows)} bağlantıdan ilan verisi alındı; {skipped} bağlantı atlandı." if skipped else f"{len(rows)} bağlantıdan ilan verisi alındı."
    else:
        blocked = sum(result["status"] == "blocked" for result in results)
        source.status = STATE_ACCESS_DENIED if blocked == len(results) else STATE_ERROR
        source.status_message = f"İlan verisi alınamadı; {blocked} bağlantıda erişim kısıtı görüldü."
    source.last_checked_at = utcnow()
    db.commit()
    return {
        "id": batch.id if batch else None,
        "row_count": len(rows),
        "results": results,
    }


@router.delete("/imports/{batch_id}")
def delete_import(batch_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Dosya kaydı bulunamadı.")
    db.delete(batch)
    db.commit()
    return {"ok": True}
