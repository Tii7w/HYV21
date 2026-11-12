"""
HKY Estates V2 - Uygulama girişi
Geliştirmede Vite ayrı çalışır; üretimde derlenmiş frontend buradan sunulur.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent.runner import manager
from .api import agent, auth, catalog, listings, notifications, profiles, settings
from .config import FRONTEND_DIST
from .db import SessionLocal
from .security import _secret_bytes
from .settings_store import seed_defaults

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    ),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _secret_bytes()  # Anahtar yoksa sunucu başlamadan anlaşılır bir hata verir.
    with SessionLocal() as db:
        seed_defaults(db)
    manager.start_worker()
    yield
    manager.shutdown()


app = FastAPI(title="HKY Estates V2", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
for module in (auth, catalog, listings, profiles, agent, settings, notifications):
    app.include_router(module.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Bulunamadı."}, status_code=404)
        target = (FRONTEND_DIST / path).resolve()
        if path and target.is_file() and FRONTEND_DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
