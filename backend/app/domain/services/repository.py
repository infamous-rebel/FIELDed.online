"""Service Offer domain repository.

Provides database access for ServiceCategory and ServiceOffer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.services.models import ServiceCategory, ServiceOffer


class ServiceCategoryRepository:
    """Data access for ServiceCategory entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, category_id: uuid.UUID) -> ServiceCategory | None:
        """Fetch a category by ID."""
        result = await self.session.execute(
            select(ServiceCategory).where(
                ServiceCategory.id == category_id,
                ServiceCategory.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> ServiceCategory | None:
        """Fetch a category by slug."""
        result = await self.session.execute(
            select(ServiceCategory).where(
                ServiceCategory.slug == slug,
                ServiceCategory.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[ServiceCategory]:
        """Fetch all active categories."""
        result = await self.session.execute(
            select(ServiceCategory)
            .where(ServiceCategory.deleted_at.is_(None))
            .order_by(ServiceCategory.name)
        )
        return list(result.scalars().all())

    async def get_root_categories(self) -> list[ServiceCategory]:
        """Fetch top-level categories (no parent)."""
        result = await self.session.execute(
            select(ServiceCategory)
            .where(
                ServiceCategory.parent_id.is_(None),
                ServiceCategory.deleted_at.is_(None),
            )
            .order_by(ServiceCategory.name)
        )
        return list(result.scalars().all())

    async def create(self, category: ServiceCategory) -> ServiceCategory:
        """Persist a new category."""
        self.session.add(category)
        await self.session.flush()
        return category


class ServiceOfferRepository:
    """Data access for ServiceOffer entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, offer_id: uuid.UUID) -> ServiceOffer | None:
        """Fetch a service offer by ID."""
        result = await self.session.execute(
            select(ServiceOffer)
            .where(
                ServiceOffer.id == offer_id,
                ServiceOffer.deleted_at.is_(None),
            )
            .options(selectinload(ServiceOffer.category))
        )
        return result.scalar_one_or_none()

    async def get_by_business_id(
        self, business_id: uuid.UUID
    ) -> list[ServiceOffer]:
        """Fetch all service offers for a business."""
        result = await self.session.execute(
            select(ServiceOffer)
            .where(
                ServiceOffer.business_id == business_id,
                ServiceOffer.deleted_at.is_(None),
            )
            .options(selectinload(ServiceOffer.category))
            .order_by(ServiceOffer.name)
        )
        return list(result.scalars().all())

    async def get_by_business_and_status(
        self, business_id: uuid.UUID, status: str
    ) -> list[ServiceOffer]:
        """Fetch service offers for a business filtered by status."""
        result = await self.session.execute(
            select(ServiceOffer)
            .where(
                ServiceOffer.business_id == business_id,
                ServiceOffer.status == status,
                ServiceOffer.deleted_at.is_(None),
            )
            .options(selectinload(ServiceOffer.category))
            .order_by(ServiceOffer.name)
        )
        return list(result.scalars().all())

    async def get_by_category_id(
        self, category_id: uuid.UUID
    ) -> list[ServiceOffer]:
        """Fetch all active service offers in a category."""
        result = await self.session.execute(
            select(ServiceOffer)
            .where(
                ServiceOffer.category_id == category_id,
                ServiceOffer.status == "active",
                ServiceOffer.deleted_at.is_(None),
            )
            .order_by(ServiceOffer.name)
        )
        return list(result.scalars().all())

    async def search(
        self,
        *,
        category_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[ServiceOffer]:
        """Search service offers with optional filters."""
        query = select(ServiceOffer).where(ServiceOffer.deleted_at.is_(None))

        if category_id is not None:
            query = query.where(ServiceOffer.category_id == category_id)
        if status is not None:
            query = query.where(ServiceOffer.status == status)
        else:
            query = query.where(ServiceOffer.status == "active")

        result = await self.session.execute(
            query.options(selectinload(ServiceOffer.category)).order_by(
                ServiceOffer.name
            )
        )
        return list(result.scalars().all())

    async def create(self, offer: ServiceOffer) -> ServiceOffer:
        """Persist a new service offer."""
        self.session.add(offer)
        await self.session.flush()
        return offer

    async def update(self, offer: ServiceOffer) -> ServiceOffer:
        """Update an existing service offer."""
        await self.session.flush()
        return offer
