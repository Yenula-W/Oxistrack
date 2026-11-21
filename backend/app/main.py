import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .config import get_settings
from .database import Base, engine
from .routers import analysis, auth, documents, projects

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("oxistrack")
settings = get_settings()
if settings.environment == "production" and settings.secret_key in ("dev-only-change-me", "change-me"):
    raise RuntimeError("SECRET_KEY must be set to a strong random value in production.")

app = FastAPI(title="OxisTrack API", version="1.0.0",
              description="AI-powered project intelligence and verification platform.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

if settings.auto_create_tables or settings.database_url.startswith("sqlite"):
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)

for r in (auth.router, projects.router, documents.router, analysis.router):
    app.include_router(r)


@app.exception_handler(OperationalError)
async def db_unavailable(request: Request, exc: OperationalError):
    log.error("database error on %s: %s", request.url.path, exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Please try again shortly."})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server."})


@app.get("/health", tags=["system"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})
