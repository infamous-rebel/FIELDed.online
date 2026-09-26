"""Booking automation status model.

Tracks the status of each downstream automation operation
triggered by booking lifecycle events.

Each operation is tracked independently:
- Calendar synchronization
- Service execution creation
- Payment preparation

A failure in any operation does NOT affect the authoritative
booking state or other operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.common.base_model import BaseModel


class BookingAutomationStatus(BaseModel):
    """Tracks downstream automation operation status per booking.

    One record per (booking_id, operation_type) combination.
    Updated on each attempt; status reflects the latest outcome.

    Lifecycle:
        PENDING → SUCCESS
        PENDING → FAILED → SUCCESS (retry)
        PENDING → FAILED → EXHAUSTED (max retries)
        PENDING → NOT_APPLICABLE (operation not needed)
    """

    __tablename__ = "booking_automation_status"
    __table_args__ = (
        Index("ix_bas_business_id", "business_id"),
        Index("ix_bas_booking_id", "booking_id"),
        Index("ix_bas_status", "status"),
        Index("ix_bas_operation_booking", "operation_type", "booking_id", unique=True),
        Index("ix_bas_retry", "status", "next_retry_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Operation type: CALENDAR_SYNC, SERVICE_EXECUTION, PAYMENT_PREP
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Triggering outbox event type (e.g., BOOKING_CONFIRMED)
    triggering_event: Mapped[str] = mapped_column(String(100), nullable=False)

    # Status: PENDING, SUCCESS, FAILED, NOT_APPLICABLE, EXHAUSTED
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Provider reference or operation-specific evidence
    result_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
