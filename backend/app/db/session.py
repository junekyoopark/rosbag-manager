from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for Celery workers
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    pool_pre_ping=True,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)
