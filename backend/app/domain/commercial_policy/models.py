"""Commercial Policy domain model.

A CommercialPolicy defines the FIELDed platform fee rules for a
given scope (global, category, business plan, promotion, or
negotiated business-specific agreement).

Policies are versioned and time-bounded (effective_from / effective_until).
Only one ACTIVE policy per scope+target combination is effective at any
point in time.  The Fee Engine resolves the highest-precedence active
policy for a given transaction context and uses it to calculate the
platform fee deterministically.

AI may read and explain policies but must NEVER create, modify,
activate, or override them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business
    from app.domain.services.models import ServiceCategory


class CommercialPolicy(BaseModel):
    """A versioned FIELDed commercial policy rule.

    Precedence (highest → lowest):
        business_specific  → promotion → business_plan →
        category_default  → global_default

    A policy is effective for transactions where:
    - status = ACTIVE
    - now is within [effective_from, effective_until)
    - the scope/target matches the transaction context
      (business_id, category_id, promotion_code, etc.)
    """

    __tablename__ = "commercial_policies"
    __table_args__ = (
        # Only one active policy per scope + target at a time.
        # Enforced at application level (not DB unique) because
        # effective_from/until create overlapping windows.
        Index("ix_commercial_policies_scope_status", "scope", "status"),
        Index("ix_commercial_policies_business_id", "business_id"),
        Index("ix_commercial_policies_category_id", "category_id"),
        Index("ix_commercial_policies_effective", "effective_from", "effective_until"),
        # Unique version per scope + name
        UniqueConstraint(
            "scope", "name", "version",
            name="uq_commercial_policy_scope_name_version",
        ),
    )

    # ── Identity ──────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # CommercialPolicyScope enum value
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Scope target (which business / category / plan this applies to) ──
    # Null means "all" within the scope tier.
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Business plan identifier (free-form string key, e.g. "premium", "enterprise")
    plan_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Promotion code (for promotion scope)
    promotion_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )

    # ── Fee structure ─────────────────────────────────────────────
    fee_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # CommercialPolicyFeeType enum value

    # Percentage component (0–100).  Used for PERCENTAGE and COMBINED.
    percentage: Mapped[str] = mapped_column(
        Numeric(precision=7, scale=4), nullable=False, default="0.0000"
    )
    # Fixed component (absolute currency amount).  Used for FIXED and COMBINED.
    fixed_amount: Mapped[str] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False, default="0.00"
    )
    # Currency for the fixed component (ISO 4217).
    fixed_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="GBP"
    )

    # ── Time bounds ───────────────────────────────────────────────
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Lifecycle ─────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # CommercialPolicyStatus enum value

    # ── Eligibility criteria (JSONB) ──────────────────────────────
    # Structured criteria for volume-based or segment-based eligibility.
    # Examples:
    #   {"min_transactions_per_month": 100}
    #   {"customer_segments": ["enterprise"]}
    #   {"max_transaction_amount": "10000.00"}
    eligibility: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Display / disclosure ──────────────────────────────────────
    # Human-readable disclosure shown to the customer / business.
    # Example: "FIELDed platform fee: 2% per completed transaction.
    #           Stripe processing fees apply separately."
    disclosure: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Configuration metadata ────────────────────────────────────
    # Extra structured data for future extensibility.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Soft-delete flag (explicit) ───────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ─────────────────────────────────────────────
    business: Mapped[Business | None] = relationship(foreign_keys=[business_id])
    category: Mapped[ServiceCategory | None] = relationship(foreign_keys=[category_id])
