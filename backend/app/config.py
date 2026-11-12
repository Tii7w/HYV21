"""
HKY Estates V2 - Yapılandırma
Tüm gizli değerler ortam değişkenlerinden (.env) okunur; kodda veya frontend'de tutulmaz.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
DATA_DIR = BACKEND_DIR / "data"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = f"sqlite:///{(DATA_DIR / 'hky.db').as_posix()}"
    hky_secret_key: str = ""
    admin_email: str = "admin@hky.local"
    admin_password: str = ""
    cookie_secure: bool = False
    session_hours: int = 24

    sahibinden_api_base_url: Optional[str] = None
    sahibinden_api_key: Optional[str] = None

    @field_validator("database_url")
    @classmethod
    def _default_database(cls, value: str) -> str:
        # .env içinde boş bırakılan satır varsayılan SQLite dosyasını kullanır.
        return value or f"sqlite:///{(DATA_DIR / 'hky.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
