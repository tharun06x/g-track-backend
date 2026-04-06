import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()
db_url = os.getenv("SQLALCHEMY_DATABASE_URL")
if not db_url:
    raise RuntimeError("SQLALCHEMY_DATABASE_URL is not configured")

engine: AsyncEngine = create_async_engine(
    db_url,
    pool_pre_ping=True,
    echo=True,
    connect_args={"ssl": True}
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
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
    