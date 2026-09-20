"""Service Category API endpoints.

Provides read-only access to service categories.
Categories are platform-managed and publicly readable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.services.schemas import ServiceCategoryRead
from app.domain.services.service import ServiceCategoryService

router = APIRouter()


@router.get("", response_model=list[ServiceCategoryRead])
async def list_categories(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ServiceCategoryRead]:
    """List all service categories.

    Returns a flat list of all categories.
    Categories are publicly readable for the future discovery engine.
    """
    service = ServiceCategoryService(db)
    categories = await service.get_all_categories()
    return [
        ServiceCategoryRead(
            id=c.id,
            name=c.name,
            slug=c.slug,
            description=c.description,
            parent_id=c.parent_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in categories
    ]


@router.get("/roots", response_model=list[ServiceCategoryRead])
async def list_root_categories(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ServiceCategoryRead]:
    """List top-level categories (no parent)."""
    service = ServiceCategoryService(db)
    categories = await service.get_root_categories()
    return [
        ServiceCategoryRead(
            id=c.id,
            name=c.name,
            slug=c.slug,
            description=c.description,
            parent_id=c.parent_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in categories
    ]
