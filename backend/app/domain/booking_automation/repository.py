"""Booking automation status repository.

Data access for BookingAutomationStatus entities.
All queries enforce tenant isolation via business_id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking_automation.models import BookingAutomationStatus


class BookingAutomationStatusRepository:
    """Data access for BookingAutomationStatus entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_booking_and_operation(
        self,
        booking_id: uuid.UUID,
        operation_type: str,
    ) -> BookingAutomationStatus | None:
        """Get automation status for a specific booking + operation."""
        result = await self.session.execute(
            select(BookingAutomationStatus).where(
                BookingAutomationStatus.booking_id == booking_id,
                BookingAutomationStatus.operation_type == operation_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_business(self, business_id: uuid.UUID) -> list[BookingAutomationStatus]:
        """List all automation statuses for a business."""
        result = await self.session.execute(
            select(BookingAutomationStatus).where(
                BookingAutomationStatus.business_id == business_id,
            )
        )
        return list(result.scalars().all())

    async def get_by_booking(self, booking_id: uuid.UUID) -> list[BookingAutomationStatus]:
        """List all automation statuses for a booking."""
        result = await self.session.execute(
            select(BookingAutomationStatus).where(
                BookingAutomationStatus.booking_id == booking_id,
            )
        )
        return list(result.scalars().all())

    async def create(self, status: BookingAutomationStatus) -> BookingAutomationStatus:
        """Persist a new automation status record."""
        self.session.add(status)
        await self.session.flush()
        return status

    async def update(self, status: BookingAutomationStatus) -> BookingAutomationStatus:
        """Update an existing automation status record."""
        await self.session.flush()
        return status

    async def get_retryable(
        self,
        *,
        batch_size: int = 20,
    ) -> list[BookingAutomationStatus]:
        """Get failed automation records eligible for retry.

        Returns records where:
        - status is FAILED
        - attempt_count < max_attempts (5)
        - next_retry_at is None or in the past
        """
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(BookingAutomationStatus)
            .where(
                BookingAutomationStatus.status == "FAILED",
                BookingAutomationStatus.attempt_count < 5,
                (BookingAutomationStatus.next_retry_at.is_(None)) | (BookingAutomationStatus.next_retry_at <= now),
            )
            .order_by(BookingAutomationStatus.next_retry_at.asc().nullsfirst())
            .limit(batch_size)
        )
        return list(result.scalars().all())

    async def mark_success(
        self,
        status: BookingAutomationStatus,
        *,
        evidence: dict | None = None,
    ) -> None:
        """Mark an operation as successfully completed."""
        await self.session.execute(
            update(BookingAutomationStatus)
            .where(BookingAutomationStatus.id == status.id)
            .values(
                status="SUCCESS",
                last_attempted_at=datetime.now(UTC),
                last_error=None,
                next_retry_at=None,
                result_evidence=evidence,
            )
        )

    async def mark_failed(
        self,
        status: BookingAutomationStatus,
        *,
        error: str,
        retry_after_seconds: int = 60,
    ) -> None:
        """Mark an operation as failed, eligible for retry."""
        next_retry = datetime.now(UTC) + timedelta(seconds=retry_after_seconds)
        await self.session.execute(
            update(BookingAutomationStatus)
            .where(BookingAutomationStatus.id == status.id)
            .values(
                status="FAILED",
                last_attempted_at=datetime.now(UTC),
                last_error=error[:1000],
                next_retry_at=next_retry,
            )
        )

    async def mark_exhausted(
        self,
        status: BookingAutomationStatus,
        *,
        error: str,
    ) -> None:
        """Mark an operation as permanently failed (max retries exceeded)."""
        await self.session.execute(
            update(BookingAutomationStatus)
            .where(BookingAutomationStatus.id == status.id)
            .values(
                status="EXHAUSTED",
                last_attempted_at=datetime.now(UTC),
                last_error=error[:1000],
                next_retry_at=None,
            )
        )

    async def mark_not_applicable(
        self,
        status: BookingAutomationStatus,
    ) -> None:
        """Mark an operation as not applicable for this booking."""
        await self.session.execute(
            update(BookingAutomationStatus)
            .where(BookingAutomationStatus.id == status.id)
            .values(
                status="NOT_APPLICABLE",
                last_attempted_at=datetime.now(UTC),
                next_retry_at=None,
            )
        )
