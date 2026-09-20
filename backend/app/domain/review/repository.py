"""Review domain repository.

Provides database access for Review entities.
All queries enforce tenant isolation and soft-delete filtering.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.review.models import Review


class ReviewRepository:
    """Data access for Review entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, review: Review) -> Review:
        """Persist a new review."""
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_by_id(self, review_id: uuid.UUID) -> Review | None:
        """Fetch a review by ID."""
        result = await self.session.execute(
            select(Review).where(
                Review.id == review_id,
                Review.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_service_execution(
        self, service_execution_id: uuid.UUID
    ) -> Review | None:
        """Fetch the review for a service execution (UNIQUE constraint)."""
        result = await self.session.execute(
            select(Review).where(
                Review.service_execution_id == service_execution_id,
                Review.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Review]:
        """Fetch reviews submitted by a customer."""
        stmt = (
            select(Review)
            .where(
                Review.customer_id == customer_id,
                Review.deleted_at.is_(None),
            )
            .order_by(Review.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Review]:
        """Fetch reviews for a business (tenant-scoped)."""
        stmt = (
            select(Review)
            .where(
                Review.business_id == business_id,
                Review.deleted_at.is_(None),
            )
            .order_by(Review.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Review.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_visible_by_business_slug(
        self,
        business_slug: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Review]:
        """Fetch visible reviews for a business by slug (public)."""
        from app.domain.identity.models import Business, BusinessProfile

        stmt = (
            select(Review)
            .join(Business, Review.business_id == Business.id)
            .where(
                Business.slug == business_slug,
                Review.status == "visible",
                Review.deleted_at.is_(None),
            )
            .order_by(Review.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_average_rating_for_business(
        self, business_id: uuid.UUID
    ) -> tuple[float | None, int]:
        """Calculate average rating and count for a business.

        Returns (average_rating, review_count) from visible reviews.
        """
        result = await self.session.execute(
            select(
                func.avg(Review.rating),
                func.count(Review.id),
            ).where(
                Review.business_id == business_id,
                Review.status == "visible",
                Review.deleted_at.is_(None),
            )
        )
        row = result.one()
        avg_rating = float(row[0]) if row[0] is not None else None
        count = int(row[1])
        return avg_rating, count

    async def update(self, review: Review) -> Review:
        """Update an existing review."""
        await self.session.flush()
        return review
