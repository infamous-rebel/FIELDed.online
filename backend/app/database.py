"""Database engine, session factory, and lifecycle management.

Uses SQLAlchemy 2.0 async with asyncpg driver.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(settings: Settings) -> AsyncEngine:
    """Create and configure the async database engine."""
    global _engine, _session_factory

    _engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.app_debug,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info("database_engine_created", url=settings.database_url.split("@")[-1])
    return _engine


def get_engine() -> AsyncEngine:
    """Return the configured database engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the configured session factory."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db first.")
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a database session per request."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health(engine: AsyncEngine) -> bool:
    """Check database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))
        return False


async def dispose_engine() -> None:
    """Dispose the database engine (for shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_engine_disposed")
