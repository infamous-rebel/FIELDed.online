"""Identity domain models.

Canonical entities: User, CustomerProfile, Business, BusinessMember.

User is the authentication identity.
CustomerProfile and Business are operational roles.
BusinessMember links a User to a Business with a specific role.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.services.models import ServiceOffer


class User(BaseModel):
    """Authentication identity.

    A User can have multiple roles (customer, business member, etc.)
    but is always a single authentication identity.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    customer_profile: Mapped[CustomerProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    business_memberships: Mapped[list[BusinessMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class CustomerProfile(BaseModel):
    """Customer-side profile.

    Linked 1:1 to a User. Contains customer-specific information.
    """

    __tablename__ = "customer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="incomplete"
    )  # CustomerProfileStatus enum value

    # Relationships
    user: Mapped[User] = relationship(back_populates="customer_profile")


class Business(BaseModel):
    """A business entity on the platform.

    A Business has a public profile, a Business Brain, and Service Offers.
    It is operated by one or more BusinessMembers.
    """

    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # BusinessStatus enum value

    # Operational currency — the business's default currency for transactions.
    # ISO 4217 code (e.g. "GBP", "USD", "EUR").  Must be explicit; no silent defaults.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # ── Stripe Connect (payment processing) ──────────────────────────
    # The connected Stripe account ID (e.g. acct_xxx).  Null until the
    # business completes Stripe onboarding.
    stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Onboarding / capability status (mirrors Stripe account capabilities).
    stripe_connect_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="none"
    )  # StripeConnectAccountStatus enum value

    # Granular capability flags from Stripe account capabilities.
    stripe_charges_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stripe_payouts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Detailed Stripe account snapshot for audit/debugging.
    stripe_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Platform application fee percentage (0–100).  Applied as
    # application_fee_amount on Direct Charges.
    platform_fee_percent: Mapped[str] = mapped_column(Numeric(precision=5, scale=2), nullable=False, default="0.00")

    # Relationships
    members: Mapped[list[BusinessMember]] = relationship(back_populates="business", cascade="all, delete-orphan")
    profile: Mapped[BusinessProfile | None] = relationship(
        back_populates="business", uselist=False, cascade="all, delete-orphan"
    )
    service_offers: Mapped[list[ServiceOffer]] = relationship(back_populates="business", cascade="all, delete-orphan")


class BusinessProfile(BaseModel):
    """Public business profile.

    Contains all information visible to customers and the platform.
    """

    __tablename__ = "business_profiles"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Location
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Social links
    facebook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Trust signals
    average_rating: Mapped[float | None] = mapped_column(nullable=True)
    review_count: Mapped[int] = mapped_column(default=0, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Public profile status
    public_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="incomplete"
    )  # BusinessProfileStatus enum value

    # Service area (structured geographic data)
    service_area: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    business: Mapped[Business] = relationship(back_populates="profile")


class BusinessMember(BaseModel):
    """Links a User to a Business with a specific role.

    A User can be a member of multiple businesses.
    A Business can have multiple members.
    """

    __tablename__ = "business_members"
    __table_args__ = (UniqueConstraint("user_id", "business_id", name="uq_business_member_user_business"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="staff")  # BusinessMemberRole enum value

    # Relationships
    user: Mapped[User] = relationship(back_populates="business_memberships")
    business: Mapped[Business] = relationship(back_populates="members")
