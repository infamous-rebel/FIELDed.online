"""Database engine, session factory, and lifecycle management.

Uses SQLAlchemy 2.0 async with asyncpg driver.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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


def _prepare_neon_url(url: str) -> tuple[str, dict]:
    """Prepare database URL for asyncpg compatibility.

    asyncpg does not accept sslmode/channel_binding as URL query parameters.
    For Neon (and other SSL-required hosts), strip those params and pass
    SSL via connect_args instead.

    Returns:
        Tuple of (cleaned_url, connect_args dict)
    """
    connect_args: dict = {}
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # Check if SSL is required (Neon always requires it)
    sslmode = query_params.pop("sslmode", [None])[0]
    query_params.pop("channel_binding", None)  # Remove channel_binding

    if sslmode and sslmode != "disable":
        connect_args["ssl"] = sslmode

    # Rebuild URL without sslmode/channel_binding
    new_query = urlencode(query_params, doseq=True)
    clean_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )

    return clean_url, connect_args


def init_db(settings: Settings) -> AsyncEngine:
    """Create and configure the async database engine."""
    global _engine, _session_factory

    db_url, connect_args = _prepare_neon_url(settings.database_url)

    _engine = create_async_engine(
        db_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.app_debug,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info("database_engine_created", url=settings.database_url.split("@")[-1])
    return _engine


def build_engine(url: str, **engine_kwargs: Any) -> AsyncEngine:
    """Build a standalone engine with asyncpg SSL compatibility applied.

    Use this for CLI entry points (workers, seed scripts) that create
    their own engine outside the application lifecycle.
    """
    clean_url, connect_args = _prepare_neon_url(url)
    extra_connect_args = engine_kwargs.pop("connect_args", {})
    connect_args.update(extra_connect_args)
    engine_kwargs.setdefault("pool_pre_ping", True)
    return create_async_engine(clean_url, connect_args=connect_args, **engine_kwargs)


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
