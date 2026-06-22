from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DB_PATH

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Async engine for startup (table creation)
async_engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)

# Sync engine for endpoint database sessions
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
