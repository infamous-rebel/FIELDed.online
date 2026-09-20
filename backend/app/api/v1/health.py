"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import check_db_health, get_engine

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check() -> dict[str, str]:
    """Readiness probe — checks database connectivity."""
    engine = get_engine()
    db_healthy = await check_db_health(engine)

    status = "ok" if db_healthy else "degraded"
    return {
        "status": status,
        "database": "ok" if db_healthy else "unavailable",
    }
