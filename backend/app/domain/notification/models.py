"""Notification domain model.

A Notification represents an event informing a recipient.
It is distinct from the actual communication performed through
a channel provider.

Phase 14A — Core Communications, Notifications & Provider Adapters.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business, User


class Notification(BaseModel):
    """Persisted notification record.

    Notifications are created from domain events and inform recipients
    about operational changes.  The actual communication (email, SMS, etc.)
    is a separate concern handled by the Communication domain.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_business_id", "business_id"),
        Index("ix_notifications_customer_id", "customer_id"),
        Index("ix_notifications_type", "notification_type"),
        # Efficient unread queries
        Index("ix_notifications_customer_unread", "customer_id", "read_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(50), nullable=False, default="NORMAL"
    )

    # Idempotency — unique constraint prevents duplicate notifications
    # when an outbox event is retried after a worker crash
    idempotency_key: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False
    )

    # Related entity tracking
    related_entity_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Read state
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_state: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # Relationships
    business: Mapped["Business"] = relationship(foreign_keys=[business_id])
    customer: Mapped["User | None"] = relationship(foreign_keys=[customer_id])
