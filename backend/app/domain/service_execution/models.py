"""Service Execution domain model.

A ServiceExecution represents the actual delivery of a booked service.
It is created from a confirmed booking and tracks the service through
its operational lifecycle until completion (or cancellation/no-show).

Every completed ServiceExecution produces exactly one Invoice and one
primary ServiceLedgerEntry, ensuring financial traceability.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.booking.models import Booking
    from app.domain.identity.models import Business, User
    from app.domain.invoice.models import Invoice
    from app.domain.ledger.models import ServiceLedgerEntry
    from app.domain.quote.models import Quote
    from app.domain.services.models import ServiceOffer


class ServiceExecution(BaseModel):
    """The actual delivery of a booked service.

    Lifecycle:
        SCHEDULED -> IN_PROGRESS -> COMPLETED

    Exception states:
        CANCELLED, NO_SHOW

    Completion is idempotent — repeated completion requests must not
    create duplicate downstream invoices or ledger entries.
    """

    __tablename__ = "service_executions"
    __table_args__ = (
        Index("ix_service_executions_business_id", "business_id"),
        Index("ix_service_executions_customer_id", "customer_id"),
        Index("ix_service_executions_booking_id", "booking_id"),
        Index("ix_service_executions_status", "status"),
    )

    # Relationship anchors — server-resolved
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,  # One execution per booking
    )
    service_offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_offers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="scheduled"
    )  # ServiceExecutionStatus enum value

    # Timestamps for service delivery
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Completion actor — who marked the service as completed
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Completion evidence / reference
    completion_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    business: Mapped["Business"] = relationship(foreign_keys=[business_id])
    customer: Mapped["User"] = relationship(foreign_keys=[customer_id])
    booking: Mapped["Booking"] = relationship(foreign_keys=[booking_id])
    service_offer: Mapped["ServiceOffer"] = relationship(foreign_keys=[service_offer_id])
    quote: Mapped["Quote | None"] = relationship(foreign_keys=[quote_id])
    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="service_execution", cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list["ServiceLedgerEntry"]] = relationship(
        back_populates="service_execution", cascade="all, delete-orphan"
    )
