"""Commercial Policy Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _stringify_decimal(v):
    """Coerce Decimal/NUMERIC to string for JSON output."""
    return str(v) if v is not None else v


# ── Request schemas ───────────────────────────────────────────────


class CommercialPolicyCreate(BaseModel):
    """Create a new commercial policy."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scope: str = Field(
        pattern=r"^(global_default|category_default|business_plan|promotion|business_specific)$",
    )
    version: int = Field(default=1, ge=1)

    # Scope targets (optional)
    business_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    plan_key: str | None = None
    promotion_code: str | None = None

    # Fee structure
    fee_type: str = Field(
        pattern=r"^(percentage|fixed|combined|zero)$",
    )
    percentage: str = Field(default="0.0000")
    fixed_amount: str = Field(default="0.00")
    fixed_currency: str = Field(default="GBP", max_length=3)

    # Time bounds
    effective_from: datetime
    effective_until: datetime | None = None

    # Eligibility / disclosure / config
    eligibility: dict | None = None
    disclosure: str | None = None
    config: dict | None = None


class CommercialPolicyUpdate(BaseModel):
    """Update an existing commercial policy (draft only)."""

    description: str | None = None
    percentage: str | None = None
    fixed_amount: str | None = None
    fixed_currency: str | None = None
    effective_until: datetime | None = None
    eligibility: dict | None = None
    disclosure: str | None = None
    config: dict | None = None


class CommercialPolicyTransition(BaseModel):
    """Transition a commercial policy's lifecycle status."""

    target_status: str = Field(
        pattern=r"^(active|inactive|superseded)$",
    )


class PolicyResolveRequest(BaseModel):
    """Resolve the effective commercial policy for a context."""

    business_id: uuid.UUID
    category_id: uuid.UUID | None = None
    promotion_code: str | None = None
    amount: str = Field(description="Transaction amount (decimal string)")
    currency: str = Field(default="GBP", max_length=3)


# ── Response schemas ──────────────────────────────────────────────


class CommercialPolicyRead(BaseModel):
    """Commercial policy detail response."""

    id: uuid.UUID
    name: str
    description: str | None
    scope: str
    version: int

    business_id: uuid.UUID | None
    category_id: uuid.UUID | None
    plan_key: str | None
    promotion_code: str | None

    fee_type: str
    percentage: str
    fixed_amount: str
    fixed_currency: str

    effective_from: datetime
    effective_until: datetime | None

    status: str
    eligibility: dict | None
    disclosure: str | None
    config: dict | None
    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    _coerce_pct = field_validator("percentage", mode="before")(_stringify_decimal)
    _coerce_fixed = field_validator("fixed_amount", mode="before")(_stringify_decimal)


class CommercialPolicyListRead(BaseModel):
    """Summary for list views."""

    id: uuid.UUID
    name: str
    scope: str
    version: int
    fee_type: str
    percentage: str
    fixed_amount: str
    status: str
    effective_from: datetime
    effective_until: datetime | None

    model_config = {"from_attributes": True}

    _coerce_pct = field_validator("percentage", mode="before")(_stringify_decimal)
    _coerce_fixed = field_validator("fixed_amount", mode="before")(_stringify_decimal)


class FeeBreakdownRead(BaseModel):
    """Deterministic fee calculation result."""

    customer_amount: str = Field(description="Amount the customer pays (service amount)")
    platform_fee: str = Field(description="FIELDed platform fee amount")
    fee_type: str = Field(description="How the fee was calculated")
    percentage_applied: str = Field(description="Percentage component applied")
    fixed_applied: str = Field(description="Fixed component applied")
    business_proceeds: str = Field(description="Estimated amount the business receives")
    currency: str
    policy_id: uuid.UUID = Field(description="The commercial policy that governed the fee")
    policy_name: str
    policy_scope: str
    policy_version: int
    effective_from: datetime
    effective_until: datetime | None
    disclosure: str | None = Field(description="Human-readable fee disclosure")
    stripe_processing_note: str = Field(
        default="Stripe processing fees apply separately and are not included in the platform fee.",
    )

    model_config = {"from_attributes": False}


class EffectivePolicyRead(BaseModel):
    """Effective policy for a business/context — for frontend disclosure."""

    policy: CommercialPolicyRead | None = Field(description="The resolved policy, or null if none matched.")
    fee_summary: str = Field(description="Concise human-readable fee summary for display.")
    stripe_note: str = Field(
        default="Stripe processing fees apply separately.",
    )
