"""
HKY Estates V2 - Veritabanı bağlantısı
Varsayılan SQLite'tır; DATABASE_URL değiştirilerek PostgreSQL'e geçilebilir.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import DATA_DIR, get_settings


def build_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    options = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if ":memory:" in url:
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def _configure_sqlite(connection, _record) -> None:
        # WAL, agent yazarken API okumalarının kilitlenmesini önler.
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Agent iş parçacığı için kısa ömürlü oturum."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
