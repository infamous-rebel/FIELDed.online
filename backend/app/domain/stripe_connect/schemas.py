"""Stripe Connect Pydantic schemas.

Request/response schemas for the Stripe Connect API.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class StripeConnectStatusRead(BaseModel):
    """Read schema for a business's Stripe Connect status."""

    business_id: uuid.UUID
    stripe_account_id: str | None = None
    stripe_connect_status: str
    stripe_charges_enabled: bool
    stripe_payouts_enabled: bool
    stripe_details: dict[str, Any] | None = None
    platform_fee_percent: str

    model_config = {"from_attributes": True}


class StripeAccountLinkCreate(BaseModel):
    """Request to create a Stripe onboarding account link."""

    refresh_url: str = Field(..., description="URL to redirect if the link expires")
    return_url: str = Field(..., description="URL to redirect after onboarding completes")
    type: str = Field("account_onboarding", description="Account link type")


class StripeAccountLinkRead(BaseModel):
    """Response with a Stripe onboarding account link."""

    url: str
    expires_at: int | None = None
    created: int | None = None


class StripeAccountRefreshRead(BaseModel):
    """Response after refreshing Stripe account status from Stripe API."""

    business_id: uuid.UUID
    stripe_account_id: str | None = None
    stripe_connect_status: str
    stripe_charges_enabled: bool
    stripe_payouts_enabled: bool
    stripe_details: dict[str, Any] | None = None
