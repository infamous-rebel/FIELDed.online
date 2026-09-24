"""Discovery API endpoints.

Provides customer discovery: natural-language → structured intent → deterministic matching.

Endpoints:
- POST /search — natural-language discovery (AI interpretation + matching)
- POST /structured — structured discovery (skip AI, go straight to matching)

Both endpoints only return data from actual database records.
AI interpretation is used ONLY to extract structured search parameters.
"""

from __future__ import annotations

import contextlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import _resolve_discovery_ai_provider
from app.adapters.ai.base import AIProvider
from app.database import get_db_session
from app.domain.discovery import (
    DiscoveryIntent,
    DiscoveryResult,
    IntentStatus,
    LocationIntent,
    ServiceIntent,
)
from app.domain.discovery.interpreter import DiscoveryInterpreter
from app.domain.discovery.matching import DiscoveryMatchingService
from app.security.authorization import get_optional_user

router = APIRouter()


# --- Schemas ---


class DiscoverySearchRequest(BaseModel):
    """Natural-language discovery request."""

    query: str = Field(
        min_length=1,
        max_length=5000,
        description="Customer's natural-language description of what they need",
    )
    location_city: str | None = Field(default=None, max_length=100)
    location_state: str | None = Field(default=None, max_length=100)
    location_country: str | None = Field(default=None, max_length=100)


class DiscoveryStructuredRequest(BaseModel):
    """Structured discovery request — skip AI interpretation."""

    category_slug: str | None = Field(default=None, max_length=255)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    location_city: str | None = Field(default=None, max_length=100)
    location_state: str | None = Field(default=None, max_length=100)
    location_country: str | None = Field(default=None, max_length=100)


class DiscoveryResponse(BaseModel):
    """Discovery response — matched businesses with active service offers."""

    status: str
    matches: list[dict[str, Any]] = []
    total_matches: int = 0
    categories_searched: list[str] = []
    clarification: str | None = None
    intent_summary: dict[str, Any] = {}


# --- Helpers ---


def _get_ai_provider(request: Request) -> AIProvider:
    """Resolve the AI provider for the Discovery workload.

    Uses the discovery-specific resolver which checks
    DISCOVERY_AI_API_KEY / DISCOVERY_AI_BASE_URL first, then
    falls back to the global AI configuration.
    """
    return _resolve_discovery_ai_provider(request.app.state.settings)


def _result_to_response(result: DiscoveryResult) -> DiscoveryResponse:
    """Convert a DiscoveryResult to the API response schema."""
    matches = []
    for m in result.matches:
        offers = []
        for o in m.service_offers:
            offers.append(
                {
                    "id": o.id,
                    "name": o.name,
                    "slug": o.slug,
                    "description": o.description,
                    "delivery_mode": o.delivery_mode,
                    "pricing_model": o.pricing_model,
                    "category_name": o.category_name,
                    "category_slug": o.category_slug,
                    "match_reason": o.match_reason,
                }
            )
        matches.append(
            {
                "business_id": m.business_id,
                "business_name": m.business_name,
                "business_slug": m.business_slug,
                "description": m.description,
                "city": m.city,
                "state": m.state,
                "country": m.country,
                "is_verified": m.is_verified,
                "logo_url": m.logo_url,
                "service_offers": offers,
            }
        )

    intent_summary = {
        "status": result.intent.status,
        "service_name": result.intent.service.service_name,
        "category_slug": result.intent.service.category_slug,
        "keywords": result.intent.service.keywords,
    }
    if result.intent.location:
        intent_summary["location"] = {
            "city": result.intent.location.city,
            "state": result.intent.location.state,
            "country": result.intent.location.country,
        }

    return DiscoveryResponse(
        status=result.intent.status,
        matches=matches,
        total_matches=result.total_matches,
        categories_searched=result.categories_searched,
        clarification=result.intent.clarification_needed,
        intent_summary=intent_summary,
    )


# --- Endpoints ---


@router.post("/search", response_model=DiscoveryResponse)
async def search(
    body: DiscoverySearchRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DiscoveryResponse:
    """Natural-language discovery.

    1. AI interprets the customer's request into structured intent
    2. Deterministic matching finds real businesses + active offers
    3. Only public data is returned

    Available to authenticated customers and anonymous visitors.
    """
    # Get optional user (works for both authenticated and anonymous)
    user = await get_optional_user(request, db)
    customer_id = str(user.id) if user else None

    # Step 1: AI interpretation
    ai_provider = _get_ai_provider(request)
    interpreter = DiscoveryInterpreter(ai_provider)
    intent = await interpreter.interpret(body.query, customer_id)

    # Augment intent with explicit location if provided
    if body.location_city or body.location_state or body.location_country:
        intent.location = LocationIntent(
            city=body.location_city or (intent.location.city if intent.location else None),
            state=body.location_state or (intent.location.state if intent.location else None),
            country=body.location_country or (intent.location.country if intent.location else None),
        )

    # If intent is INSUFFICIENT and no keywords, return early
    if intent.status == IntentStatus.INSUFFICIENT and not intent.service.keywords:
        return DiscoveryResponse(
            status=intent.status,
            matches=[],
            total_matches=0,
            clarification=intent.clarification_needed or "Please describe what service you need.",
            intent_summary={"status": intent.status},
        )

    # Step 2: Deterministic matching
    matcher = DiscoveryMatchingService(db)
    result = await matcher.match(intent)

    return _result_to_response(result)


@router.post("/structured", response_model=DiscoveryResponse)
async def structured_search(
    body: DiscoveryStructuredRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DiscoveryResponse:
    """Structured discovery — skip AI interpretation.

    Use when the frontend already has structured search parameters
    (e.g., category selected from a dropdown, keywords from tags).
    """
    user = await get_optional_user(request, db)
    customer_id = str(user.id) if user else None

    # Build intent directly from the structured request
    import uuid as uuid_mod

    parsed_customer_id = None
    if customer_id:
        with contextlib.suppress(ValueError, TypeError):
            parsed_customer_id = uuid_mod.UUID(customer_id)

    location = None
    if body.location_city or body.location_state or body.location_country:
        location = LocationIntent(
            city=body.location_city,
            state=body.location_state,
            country=body.location_country,
        )

    intent = DiscoveryIntent(
        status=IntentStatus.COMPLETE,
        raw_query=f"category={body.category_slug} keywords={body.keywords}",
        service=ServiceIntent(
            category_slug=body.category_slug,
            keywords=body.keywords,
        ),
        location=location,
        customer_id=parsed_customer_id,
    )

    # Deterministic matching
    matcher = DiscoveryMatchingService(db)
    result = await matcher.match(intent)

    return _result_to_response(result)
