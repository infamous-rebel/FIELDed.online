"""Booking domain model.

A Booking represents a confirmed service engagement between a customer
and a business.  It is created only after a Quote has been accepted.

Every Booking retains the BrainVersion ID and decision evidence that
governed its creation, ensuring historical traceability.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.business.models import BrainVersion
    from app.domain.enquiry.models import Enquiry
    from app.domain.identity.models import Business, User
    from app.domain.quote.models import Quote
    from app.domain.services.models import ServiceOffer


class Booking(BaseModel):
    """A confirmed service booking.

    Lifecycle:
        REQUESTED -> PROPOSED -> ACCEPTED -> CONFIRMED -> IN_PROGRESS -> COMPLETED

    Exception states: DECLINED, CANCELLED, EXPIRED, NO_SHOW

    The Booking retains full traceability to the BrainVersion and
    rules that governed its creation and availability evaluation.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_customer_id", "customer_id"),
        Index("ix_bookings_business_id", "business_id"),
        Index("ix_bookings_quote_id", "quote_id"),
        Index("ix_bookings_status", "status"),
    )

    # Customer-friendly reference (e.g. BKG-a1b2c3d4)
    reference: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )

    # Relationship anchors — server-resolved
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enquiries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_offers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Scheduled service time
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Transaction currency (inherited from Quote at creation time)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="GBP"
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="requested"
    )  # BookingStatus enum value

    # Brain traceability
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Decision evidence: brain decision, availability evaluation, etc.
    decision_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    customer: Mapped["User"] = relationship(foreign_keys=[customer_id])
    business: Mapped["Business"] = relationship(foreign_keys=[business_id])
    quote: Mapped["Quote"] = relationship(back_populates="bookings", foreign_keys=[quote_id])
    enquiry: Mapped["Enquiry"] = relationship(foreign_keys=[enquiry_id])
    service_offer: Mapped["ServiceOffer"] = relationship(foreign_keys=[service_offer_id])
    brain_version: Mapped["BrainVersion | None"] = relationship(
        foreign_keys=[brain_version_id]
    )
