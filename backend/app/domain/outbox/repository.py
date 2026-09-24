"""Outbox domain repository.

Provides database access for OutboxEvent entities.
Supports concurrent claiming via SELECT ... FOR UPDATE SKIP LOCKED.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.outbox.models import OutboxEvent


class OutboxRepository:
    """Data access for OutboxEvent entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: OutboxEvent) -> OutboxEvent:
        """Persist a new outbox event."""
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_idempotency_key(self, idempotency_key: str) -> OutboxEvent | None:
        """Fetch an outbox event by idempotency key."""
        result = await self.session.execute(select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key))
        return result.scalar_one_or_none()

    async def claim_pending_events(
        self,
        *,
        batch_size: int = 10,
        lease_seconds: int = 300,
    ) -> list[OutboxEvent]:
        """Claim pending/retryable events for processing.

        Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent
        claiming.  Returns claimed events already updated to PROCESSING
        status within the same transaction.

        Also reclaims stuck PROCESSING events past the lease expiry.
        """
        now = datetime.now(UTC)
        lease_cutoff = now - timedelta(seconds=lease_seconds)

        # First, reclaim stuck PROCESSING events
        await self.session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.status == "PROCESSING",
                OutboxEvent.processing_started_at < lease_cutoff,
            )
            .values(
                status="RETRYABLE",
                available_at=now,
                processing_started_at=None,
            )
        )

        # Claim pending/retryable events
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_(["PENDING", "RETRYABLE"]),
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())

        # Update claimed events to PROCESSING
        for event in events:
            event.status = "PROCESSING"
            event.processing_started_at = now
            event.attempt_count += 1

        if events:
            await self.session.flush()

        return events

    async def mark_processed(self, event_id: uuid.UUID) -> None:
        """Mark an event as successfully processed."""
        await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status="PROCESSED",
                processed_at=datetime.now(UTC),
                processing_started_at=None,
            )
        )

    async def mark_retryable(
        self,
        event_id: uuid.UUID,
        *,
        error: str,
        retry_after_seconds: int = 60,
    ) -> None:
        """Mark an event for retry."""
        available_at = datetime.now(UTC) + timedelta(seconds=retry_after_seconds)
        await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status="RETRYABLE",
                last_error=error,
                available_at=available_at,
                processing_started_at=None,
            )
        )

    async def mark_failed(self, event_id: uuid.UUID, *, error: str) -> None:
        """Mark an event as permanently failed."""
        await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status="FAILED",
                last_error=error,
                processed_at=datetime.now(UTC),
                processing_started_at=None,
            )
        )
