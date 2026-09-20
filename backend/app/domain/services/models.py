"""Service Offer domain models.

ServiceCategory provides hierarchical classification.
ServiceOffer is the transaction anchor — the bridge between
customer intent and business capability.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business


class ServiceCategory(BaseModel):
    """Hierarchical service classification.

    Examples: "Home Services", "Electrical", "Legal Services", "Accounting".
    """

    __tablename__ = "service_categories"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    parent: Mapped[ServiceCategory | None] = relationship(
        remote_side="ServiceCategory.id", backref="children"
    )
    service_offers: Mapped[list[ServiceOffer]] = relationship(back_populates="category")


class ServiceOffer(BaseModel):
    """A structured service that a business offers.

    This is the core transaction anchor. It defines:
    - What the business provides
    - Under what conditions
    - How pricing works
    - What qualifications are needed
    - Availability rules
    """

    __tablename__ = "service_offers"
    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_service_offer_business_name"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Core fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Delivery
    delivery_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="on_site"
    )  # DeliveryMode enum value

    # Pricing
    pricing_model: Mapped[str] = mapped_column(
        String(50), nullable=False, default="quote_required"
    )  # PricingModel enum value
    pricing_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Qualification requirements
    qualification_requirements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Booking rules
    booking_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Cancellation policy
    cancellation_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Service area (geographic constraints)
    service_area: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # ServiceOfferStatus enum value

    # Relationships
    business: Mapped[Business] = relationship(back_populates="service_offers")
    category: Mapped[ServiceCategory | None] = relationship(back_populates="service_offers")
