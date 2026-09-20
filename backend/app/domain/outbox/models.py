"""Outbox domain model.

The outbox_events table implements the Transactional Outbox pattern.
Domain changes and their corresponding outbox events are committed
in the same PostgreSQL transaction, ensuring at-least-once delivery
without external messaging infrastructure.

Phase 14A — Core Communications, Notifications & Provider Adapters.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.common.base_model import BaseModel


class OutboxEvent(BaseModel):
    """Transactional outbox event.

    Lifecycle:
        PENDING → PROCESSING → PROCESSED
                             → RETRYABLE → PROCESSING (retry)
                                         → FAILED (max attempts)

    No soft deletion — this is an operational record.
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_business_id", "business_id"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
        # Efficient polling: find pending/retryable events by availability
        Index("ix_outbox_status_available", "status", "available_at"),
        Index("ix_outbox_event_type", "event_type"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Idempotency — unique constraint prevents duplicate events
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)

    # Processing lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lease/recovery: track when processing started
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
