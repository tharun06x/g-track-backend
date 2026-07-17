"""
main.py — FastAPI application factory for G-Track.

Issues fixed:
  - Issue 3:  JWT secret is validated at startup — if missing or too short,
              the server refuses to start rather than running insecurely.
  - Issue 16: Documents the correct production CMD (gunicorn + UvicornWorker).
              See Dockerfile for the actual CMD change.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import close_db, init_db
from routers import dashboard, refill, report, sensor, settings, users, distributor, admin, complaints

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _validate_startup_config() -> None:
    """Fail fast if critical environment variables are missing or insecure."""
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret or len(jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing or too short (minimum 32 characters). "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    db_url = os.getenv("SQLALCHEMY_DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("SQLALCHEMY_DATABASE_URL is not configured.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _validate_startup_config()
    logger.info("G-Track API starting up...")
    await init_db()
    logger.info("Database initialised.")
    yield
    logger.info("G-Track API shutting down...")
    await close_db()


app = FastAPI(
    lifespan=lifespan,
    title="G-Track API",
    description="IoT LPG Gas Cylinder Monitoring System",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Note: "null" origin (file:// testing) is intentionally kept for local dev.
# Remove it in a strict production deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:4173",
        "http://localhost:8000",
        "http://localhost",
        "http://127.0.0.1",
        "null",
    ],
    allow_origin_regex=r"https://.*(onrender\.com|vercel\.app|netlify\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(dashboard.router)
app.include_router(distributor.router)
app.include_router(admin.router)
app.include_router(complaints.router)
app.include_router(refill.router)
app.include_router(report.router)
app.include_router(sensor.router)
app.include_router(settings.router)
app.include_router(users.router)

api_version = "1.0.0"


@app.get("/", include_in_schema=False, name="home")
def root():
    return {"status": f"G-Track {api_version} API Running"}


@app.get("/health", tags=["ops"])
async def health():
    """Health check used by Render, Docker HEALTHCHECK, and uptime monitors."""
    return {
        "status": "ok",
        "version": api_version,
    }


# ---------------------------------------------------------------------------
# Production startup command (used in Dockerfile):
#
#   gunicorn main:app \
#       -w 1 \
#       -k uvicorn.workers.UvicornWorker \
#       --bind 0.0.0.0:8000 \
#       --timeout 60 \
#       --graceful-timeout 30 \
#       --keep-alive 5 \
#       --log-level info
#
# Why 1 worker on Render Free Tier?
#   Multiple workers each maintain their own DB connection pool.
#   2 workers × pool_size=3 = 6 persistent connections.
#   Render free PostgreSQL has only 25 connections total.
#   One gunicorn worker with uvicorn's async event loop handles
#   concurrent I/O-bound requests efficiently with zero extra DB cost.
# ---------------------------------------------------------------------------
