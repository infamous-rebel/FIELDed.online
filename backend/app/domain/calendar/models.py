"""Calendar integration domain models.

CalendarConnection: per-business Google Calendar OAuth link.
CalendarEventSyncRecord: per-booking calendar synchronisation audit trail.

FIELDed Booking remains the authoritative booking record.
Calendar events are derived from bookings — never the reverse.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.common.base_model import BaseModel


class CalendarConnection(BaseModel):
    """A business's Google Calendar OAuth connection.

    One active connection per business.  Stores encrypted OAuth tokens
    so the platform can create/update/delete events on the business's
    calendar.

    Lifecycle:
        CONNECTING -> ACTIVE -> DISCONNECTED
    """

    __tablename__ = "calendar_connections"
    __table_args__ = (
        Index("ix_calconn_business_id", "business_id"),
        Index("ix_calconn_status", "status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one connection per business
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False, default="primary")
    calendar_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Encrypted OAuth tokens (Fernet-encrypted at rest)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Google account metadata (non-secret)
    google_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="connecting")

    # Last error from the provider
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarEventSyncRecord(BaseModel):
    """Per-booking calendar synchronisation record.

    Tracks the relationship between a FIELDed booking and its
    Google Calendar event.  Provides idempotent event creation
    through the deterministic booking_event_id.

    Sync status lifecycle:
        PENDING -> SYNCED
        PENDING -> FAILED -> SYNCED (retry)
    """

    __tablename__ = "calendar_event_sync_records"
    __table_args__ = (
        Index("ix_calsync_business_id", "business_id"),
        Index("ix_calsync_booking_id", "booking_id"),
        Index("ix_calsync_status", "status"),
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

    # Deterministic FIELDed booking-derived event identifier.
    # Ensures retries cannot create duplicate events.
    booking_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    # Google Calendar event ID (returned by the API after first sync)
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False, default="primary")

    # Sync lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Snapshot of the event data sent to the provider (for debugging/audit)
    sync_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
