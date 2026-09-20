"""Quote domain repository.

Provides database access for Quote entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.quote.models import Quote


class QuoteRepository:
    """Data access for Quote entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, quote_id: uuid.UUID) -> Quote | None:
        """Fetch a quote by ID."""
        result = await self.session.execute(
            select(Quote)
            .where(Quote.id == quote_id, Quote.deleted_at.is_(None))
            .options(
                selectinload(Quote.enquiry),
                selectinload(Quote.service_offer),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Quote]:
        """Fetch quotes for a customer."""
        stmt = (
            select(Quote)
            .where(
                Quote.customer_id == customer_id,
                Quote.deleted_at.is_(None),
            )
            .options(
                selectinload(Quote.enquiry),
                selectinload(Quote.service_offer),
            )
            .order_by(Quote.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Quote.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Quote]:
        """Fetch quotes for a business."""
        stmt = (
            select(Quote)
            .where(
                Quote.business_id == business_id,
                Quote.deleted_at.is_(None),
            )
            .options(
                selectinload(Quote.enquiry),
                selectinload(Quote.service_offer),
            )
            .order_by(Quote.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Quote.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_enquiry(
        self, enquiry_id: uuid.UUID
    ) -> list[Quote]:
        """Fetch all quotes for an enquiry."""
        result = await self.session.execute(
            select(Quote)
            .where(
                Quote.enquiry_id == enquiry_id,
                Quote.deleted_at.is_(None),
            )
            .order_by(Quote.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, quote: Quote) -> Quote:
        """Persist a new quote."""
        self.session.add(quote)
        await self.session.flush()
        return quote

    async def update(self, quote: Quote) -> Quote:
        """Update an existing quote."""
        await self.session.flush()
        return quote

    async def count_by_customer(self, customer_id: uuid.UUID) -> int:
        """Count quotes for a customer."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Quote)
            .where(
                Quote.customer_id == customer_id,
                Quote.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_by_business(self, business_id: uuid.UUID) -> int:
        """Count quotes for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Quote)
            .where(
                Quote.business_id == business_id,
                Quote.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
