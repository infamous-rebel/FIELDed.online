"""Discovery domain — Pydantic models for customer discovery.

Discovery is a service-layer concern, not a persistent entity.
These models represent:
- DiscoveryIntent: validated structured interpretation of a customer request
- DiscoveryMatch: a matched business + relevant active service offers
- DiscoveryResult: the complete discovery response

The AI interpreter produces a DiscoveryIntent.
The matching service consumes a DiscoveryIntent and produces a DiscoveryResult.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IntentStatus(StrEnum):
    """Outcome of AI interpretation."""

    COMPLETE = "complete"  # Fully interpreted, ready to match
    PARTIAL = "partial"  # Partially interpreted, can match with caveats
    AMBIGUOUS = "ambiguous"  # Multiple plausible interpretations
    INSUFFICIENT = "insufficient"  # Cannot reliably interpret


class LocationIntent(BaseModel):
    """Structured location extracted from customer input."""

    raw: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None


class ServiceIntent(BaseModel):
    """Structured service/category intent extracted from customer input."""

    service_name: str | None = Field(
        default=None,
        description="Name or description of the requested service",
        max_length=500,
    )
    category_slug: str | None = Field(
        default=None,
        description="Best-matching category slug if identifiable",
        max_length=255,
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for matching against service offer names/descriptions",
    )


class DiscoveryIntent(BaseModel):
    """Validated structured interpretation of a customer discovery request.

    This is the contract between the AI interpreter and the matching service.
    The AI must produce this; the matcher consumes it.

    AI must NEVER invent:
    - business IDs or names
    - service offer IDs or names
    - prices
    - availability
    - policies
    """

    status: IntentStatus = IntentStatus.COMPLETE
    raw_query: str = Field(min_length=1, max_length=5000)
    service: ServiceIntent = Field(default_factory=ServiceIntent)
    location: LocationIntent | None = None
    requested_at: datetime | None = Field(
        default=None,
        description="Requested date/time when supplied by customer",
    )
    requirements: dict[str, Any] | None = Field(
        default=None,
        description="Structured requirements extracted from the request",
    )
    clarification_needed: str | None = Field(
        default=None,
        description="Message to show the customer when status is AMBIGUOUS or INSUFFICIENT",
    )
    customer_id: uuid.UUID | None = Field(
        default=None,
        description="Requesting customer ID if authenticated",
    )


class MatchedServiceOffer(BaseModel):
    """A single ACTIVE service offer that matches the discovery intent."""

    id: str
    name: str
    slug: str
    description: str | None = None
    delivery_mode: str
    pricing_model: str
    category_name: str | None = None
    category_slug: str | None = None
    match_reason: str | None = Field(
        default=None,
        description="Why this offer matched (e.g. 'category match', 'keyword match')",
    )


class MatchedBusiness(BaseModel):
    """A business that has at least one matching ACTIVE service offer."""

    business_id: str
    business_name: str
    business_slug: str
    description: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    is_verified: bool = False
    logo_url: str | None = None
    service_offers: list[MatchedServiceOffer] = Field(default_factory=list)


class DiscoveryResult(BaseModel):
    """Complete discovery response.

    Contains matched businesses with their relevant active service offers.
    All data originates from actual database records — never from AI invention.
    """

    intent: DiscoveryIntent
    matches: list[MatchedBusiness] = Field(default_factory=list)
    total_matches: int = 0
    categories_searched: list[str] = Field(
        default_factory=list,
        description="Category slugs that were searched",
    )
