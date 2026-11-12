"""
HKY Estates V2 - Ayar ve veri kaynağı kayıtları
Şifreli alanlar buradan dışarı düz metin olarak API'ye çıkmaz.
"""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import DataSource, ScrapingSettings, User
from .schemas import AppSettings
from .security import decrypt_secret, hash_password

# Bu kaynak resmi bir API değil; tarayıcıyla açılan herkese açık arama sayfasıdır.
SAHIBINDEN_NAME = "Sahibinden.com (web sayfası)"
LEGACY_SOURCE_NAMES = {"Sahibinden.com Resmi API": SAHIBINDEN_NAME}

DEFAULT_SOURCES: List[Dict] = [
    {"key": "sahibinden", "name": SAHIBINDEN_NAME, "kind": "official_api", "enabled": False},
    {"key": "authorized", "name": "Yetkili Veri Sağlayıcı (JSON)", "kind": "authorized_feed", "enabled": False},
    {"key": "manual_import", "name": "Dosya İçe Aktarma (Excel/CSV/JSON)", "kind": "manual_import", "enabled": True},
    {"key": "demo", "name": "DEMO / Test Verisi", "kind": "demo", "enabled": False},
]


def load_settings_row(db: Session) -> ScrapingSettings:
    row = db.scalar(select(ScrapingSettings).limit(1))
    if row is None:
        row = ScrapingSettings(data=AppSettings().model_dump())
        db.add(row)
        db.commit()
    return row


def load_settings(db: Session) -> AppSettings:
    return AppSettings.model_validate(load_settings_row(db).data)


def proxy_password(db: Session) -> Optional[str]:
    return decrypt_secret(load_settings_row(db).proxy_password_encrypted)


def seed_defaults(db: Session) -> None:
    """İlk çalıştırmada kaynak ve yönetici kayıtlarını oluşturur; var olanlara dokunmaz."""
    existing = set(db.scalars(select(DataSource.key)))
    for row in db.scalars(select(DataSource).where(DataSource.name.in_(list(LEGACY_SOURCE_NAMES)))):
        row.name = LEGACY_SOURCE_NAMES[row.name]
    for source in DEFAULT_SOURCES:
        if source["key"] not in existing:
            db.add(DataSource(**source))
    load_settings_row(db)

    settings = get_settings()
    email = settings.admin_email.strip().lower()
    if settings.admin_password and db.scalar(select(User).where(User.email == email)) is None:
        db.add(User(email=email, password_hash=hash_password(settings.admin_password), role="admin"))
    db.commit()
