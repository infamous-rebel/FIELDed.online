"""Service Category API endpoints.

Provides read access to service categories plus a create endpoint
so businesses can add arbitrary classification metadata for their
services.  Categories are platform reference data — the seed supplies
broad defaults, but the system is service-agnostic and supports any
legitimate service category worldwide.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.services.schemas import ServiceCategoryRead
from app.domain.services.service import ServiceCategoryService
from app.exceptions import ConflictError
from app.security.authorization import get_current_user

router = APIRouter()


class CategoryCreateRequest(BaseModel):
    """Request body for creating a new service category."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


def _slugify(name: str) -> str:
    """Generate a URL-friendly slug from a category name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug.strip("-")


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


@router.post(
    "",
    response_model=ServiceCategoryRead,
    status_code=201,
)
async def create_category(
    body: CategoryCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[object, Depends(get_current_user)],
) -> ServiceCategoryRead:
    """Create a new service category.

    Allows authenticated users (business members) to create arbitrary
    categories so the platform remains service-agnostic.  The slug is
    auto-generated from the name.  If a category with the same slug
    already exists, the existing one is returned instead of erroring.
    """
    slug = _slugify(body.name)
    if not slug:
        from app.exceptions import ValidationError

        raise ValidationError("Category name must contain at least one alphanumeric character")

    service = ServiceCategoryService(db)

    # Idempotent: return existing category if slug matches
    try:
        category = await service.create_category(
            name=body.name,
            slug=slug,
            description=body.description,
        )
    except ConflictError:
        # Slug already exists — return the existing category
        existing = await service.get_category_by_slug(slug)
        return ServiceCategoryRead(
            id=existing.id,
            name=existing.name,
            slug=existing.slug,
            description=existing.description,
            parent_id=existing.parent_id,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    return ServiceCategoryRead(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        parent_id=category.parent_id,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )
