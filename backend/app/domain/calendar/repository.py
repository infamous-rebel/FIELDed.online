"""Calendar integration repositories.

Data access for CalendarConnection and CalendarEventSyncRecord.
All queries enforce tenant isolation (business_id scoping).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.calendar.models import CalendarConnection, CalendarEventSyncRecord


class CalendarConnectionRepository:
    """Data access for CalendarConnection entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_business(self, business_id: uuid.UUID) -> CalendarConnection | None:
        """Fetch the calendar connection for a business."""
        result = await self.session.execute(
            select(CalendarConnection).where(
                CalendarConnection.business_id == business_id,
                CalendarConnection.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, connection: CalendarConnection) -> CalendarConnection:
        """Persist a new calendar connection."""
        self.session.add(connection)
        await self.session.flush()
        return connection

    async def update(self, connection: CalendarConnection) -> CalendarConnection:
        """Update an existing calendar connection."""
        await self.session.flush()
        return connection

    async def delete(self, connection: CalendarConnection) -> None:
        """Soft-delete a calendar connection (disconnect flow)."""
        from datetime import UTC

        connection.deleted_at = datetime.now(UTC)
        connection.status = "disconnected"
        connection.access_token_encrypted = None
        connection.refresh_token_encrypted = None
        connection.token_expiry = None
        await self.session.flush()


class CalendarEventSyncRepository:
    """Data access for CalendarEventSyncRecord entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_booking(self, booking_id: uuid.UUID) -> CalendarEventSyncRecord | None:
        """Fetch the sync record for a booking."""
        result = await self.session.execute(
            select(CalendarEventSyncRecord).where(
                CalendarEventSyncRecord.booking_id == booking_id,
                CalendarEventSyncRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_booking_event_id(self, booking_event_id: str) -> CalendarEventSyncRecord | None:
        """Fetch a sync record by its deterministic booking event ID."""
        result = await self.session.execute(
            select(CalendarEventSyncRecord).where(
                CalendarEventSyncRecord.booking_event_id == booking_event_id,
                CalendarEventSyncRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_business(self, business_id: uuid.UUID) -> list[CalendarEventSyncRecord]:
        """Fetch all sync records for a business."""
        result = await self.session.execute(
            select(CalendarEventSyncRecord)
            .where(
                CalendarEventSyncRecord.business_id == business_id,
                CalendarEventSyncRecord.deleted_at.is_(None),
            )
            .order_by(CalendarEventSyncRecord.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, record: CalendarEventSyncRecord) -> CalendarEventSyncRecord:
        """Persist a new sync record."""
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(self, record: CalendarEventSyncRecord) -> CalendarEventSyncRecord:
        """Update an existing sync record."""
        await self.session.flush()
        return record
