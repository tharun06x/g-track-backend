from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine,async_sessionmaker
from sqlalchemy.orm import DeclarativeBase,sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()
db_url=os.getenv('SQLALCHEMY_DATABASE_URL')

engine=create_async_engine(db_url)
AsyncSessionLocal=async_sessionmaker(engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
    