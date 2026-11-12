import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="hky-test-"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{(TMP / 'test.db').as_posix()}",
    HKY_SECRET_KEY="t" * 48,
    ADMIN_EMAIL="admin@test.local",
    ADMIN_PASSWORD="test-pass-123",
)
sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def migrated():
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    return True


@pytest.fixture(scope="session")
def app_client(migrated):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture()
def admin(app_client):
    response = app_client.post("/api/auth/login", json={"email": "admin@test.local", "password": "test-pass-123"})
    assert response.status_code == 200, response.text
    app_client.headers["X-HKY-CSRF"] = "1"
    yield app_client
    app_client.headers.pop("X-HKY-CSRF", None)
