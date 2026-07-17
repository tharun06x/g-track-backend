"""
database.py — SQLAlchemy async engine and session factory for G-Track.

Issues fixed:
  - Issue 8: echo=True disabled in production (reads ENVIRONMENT env var).
  - Issue 9: Connection pool bounded to pool_size=3 / max_overflow=2 to prevent
             exhausting Render's free PostgreSQL (25-connection limit).
             pool_recycle=1800 prevents stale connections on long-idle instances.
"""

import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

db_url = os.getenv("SQLALCHEMY_DATABASE_URL")
if not db_url:
    raise RuntimeError("SQLALCHEMY_DATABASE_URL is not configured")

# Only log SQL in development. echo=True in production floods stdout with
# thousands of statements per minute and wastes significant CPU.
_is_development = os.getenv("ENVIRONMENT", "production").lower() == "development"

engine: AsyncEngine = create_async_engine(
    db_url,
    # ── Connection pool sizing ──────────────────────────────────────────────
    # Render free PostgreSQL allows 25 total connections across all clients.
    # Keep the pool small so migrations, admin tools, and multiple deploys
    # don't exhaust available connections.
    pool_size=3,          # Persistent connections kept in the pool
    max_overflow=2,       # Extra connections allowed during bursts (total max = 5)
    pool_timeout=30,      # Wait up to 30s for a connection before raising TimeoutError
    pool_recycle=1800,    # Recycle connections every 30 min — prevents stale TCP issues
    # ── Reliability ────────────────────────────────────────────────────────
    pool_pre_ping=True,   # Ping DB before using a pooled connection; discard if dead
    # ── Logging ────────────────────────────────────────────────────────────
    echo=_is_development, # SQL statement logging — development only
    # ── TLS ────────────────────────────────────────────────────────────────
    connect_args={"ssl": True},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session