import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DB_PATH

# Cloud PostgreSQL mode: DATABASE_URL in backend/.env switches every DB
# interaction to the cloud server (sync psycopg2 + async asyncpg drivers).
# Empty/unset → local SQLite file, the original behavior.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None

if DATABASE_URL:
    async_engine = create_async_engine(
        DATABASE_URL.replace("postgresql+psycopg2", "postgresql+asyncpg"),
        echo=False, pool_pre_ping=True)
    sync_engine = create_engine(
        DATABASE_URL, echo=False, pool_pre_ping=True)
else:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
    sync_engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
