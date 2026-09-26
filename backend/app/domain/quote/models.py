"""Quote domain model.

A Quote represents a deterministic pricing decision for an Enquiry.
It is calculated from the ServiceOffer's pricing configuration and
any applicable Business Brain pricing rules.

Every Quote retains the BrainVersion ID and pricing evidence that
governed its calculation, ensuring historical traceability even
after a newer BrainVersion becomes active.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.business.models import BrainVersion
    from app.domain.enquiry.models import Enquiry
    from app.domain.identity.models import Business, User
    from app.domain.services.models import ServiceOffer


class Quote(BaseModel):
    """A deterministic pricing decision for an enquiry.

    Lifecycle: DRAFT -> ISSUED -> ACCEPTED / DECLINED / EXPIRED

    The Quote retains full traceability to the BrainVersion and
    pricing rules that determined the amount.
    """

    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_customer_id", "customer_id"),
        Index("ix_quotes_business_id", "business_id"),
        Index("ix_quotes_enquiry_id", "enquiry_id"),
        Index("ix_quotes_status", "status"),
    )

    # Customer-friendly reference (e.g. QUO-a1b2c3d4)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

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

    # Pricing
    amount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # Lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")  # QuoteStatus enum value

    # Brain traceability
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Pricing evidence: base amount, applied rules, surcharges, discounts, etc.
    pricing_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # FIELDed commercial-policy fee evidence at quote time.
    # Stores: policy_id, policy_version, scope, fee_type, platform_fee,
    # business_proceeds, effective_from, effective_until, disclosure.
    fee_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Optional notes from the business
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    enquiry: Mapped[Enquiry] = relationship(foreign_keys=[enquiry_id])
    service_offer: Mapped[ServiceOffer] = relationship(foreign_keys=[service_offer_id])
    brain_version: Mapped[BrainVersion | None] = relationship(foreign_keys=[brain_version_id])
    bookings: Mapped[list[Booking]] = relationship(  # noqa: F821
        back_populates="quote", cascade="all, delete-orphan"
    )
