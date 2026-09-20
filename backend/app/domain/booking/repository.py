"""Booking domain repository.

Provides database access for Booking entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.booking.models import Booking


class BookingRepository:
    """Data access for Booking entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        """Fetch a booking by ID."""
        result = await self.session.execute(
            select(Booking)
            .where(Booking.id == booking_id, Booking.deleted_at.is_(None))
            .options(
                selectinload(Booking.quote),
                selectinload(Booking.enquiry),
                selectinload(Booking.service_offer),
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
    ) -> list[Booking]:
        """Fetch bookings for a customer."""
        stmt = (
            select(Booking)
            .where(
                Booking.customer_id == customer_id,
                Booking.deleted_at.is_(None),
            )
            .options(
                selectinload(Booking.quote),
                selectinload(Booking.service_offer),
            )
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Booking.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Booking]:
        """Fetch bookings for a business."""
        stmt = (
            select(Booking)
            .where(
                Booking.business_id == business_id,
                Booking.deleted_at.is_(None),
            )
            .options(
                selectinload(Booking.quote),
                selectinload(Booking.service_offer),
            )
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Booking.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_quote(self, quote_id: uuid.UUID) -> list[Booking]:
        """Fetch bookings for a quote."""
        result = await self.session.execute(
            select(Booking).where(
                Booking.quote_id == quote_id,
                Booking.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def create(self, booking: Booking) -> Booking:
        """Persist a new booking."""
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def update(self, booking: Booking) -> Booking:
        """Update an existing booking."""
        await self.session.flush()
        return booking

    async def count_by_customer(self, customer_id: uuid.UUID) -> int:
        """Count bookings for a customer."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.customer_id == customer_id,
                Booking.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_by_business(self, business_id: uuid.UUID) -> int:
        """Count bookings for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.business_id == business_id,
                Booking.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
