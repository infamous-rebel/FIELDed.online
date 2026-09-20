"""Review domain model.

A Review represents a customer's feedback on a completed service.
Reviews are linked to the full transaction chain (execution → booking →
enquiry → service offer) and are only eligible when deterministic
criteria are met.

Eligibility is never determined by AI.  The UNIQUE constraint on
service_execution_id ensures one review per completed service.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.booking.models import Booking
    from app.domain.enquiry.models import Enquiry
    from app.domain.identity.models import Business, User
    from app.domain.service_execution.models import ServiceExecution
    from app.domain.services.models import ServiceOffer


class Review(BaseModel):
    """Customer review of a completed service.

    Trust chain:
        Completed ServiceExecution
        + Valid Booking (not cancelled/declined)
        + Correct Customer (owns the transaction)
        + Correct Business (owns the execution)
        + No existing review (UNIQUE constraint)
        → Review eligible

    Eligibility is deterministic.  AI never determines review eligibility.
    """

    __tablename__ = "reviews"
    __table_args__ = (
        # One review per completed service execution
        UniqueConstraint(
            "service_execution_id",
            name="uq_reviews_service_execution_id",
        ),
        Index("ix_reviews_business_id_status", "business_id", "status"),
        Index("ix_reviews_customer_id", "customer_id"),
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
    service_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
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

    # Review content
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="visible")

    # Business response
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    responder: Mapped[User | None] = relationship(foreign_keys=[responded_by])
    service_execution: Mapped[ServiceExecution] = relationship(foreign_keys=[service_execution_id])
    booking: Mapped[Booking] = relationship(foreign_keys=[booking_id])
    enquiry: Mapped[Enquiry] = relationship(foreign_keys=[enquiry_id])
    service_offer: Mapped[ServiceOffer] = relationship(foreign_keys=[service_offer_id])
