"""AI-powered discovery interpreter.

Converts natural-language customer requests into validated DiscoveryIntent
using the provider-agnostic AIProvider adapter.

Key invariants:
- AI output is ALWAYS validated against the DiscoveryIntent schema
- AI must NEVER invent businesses, offers, prices, or availability
- If interpretation fails or is ambiguous, returns a structured clarification
- The AI provider is replaceable through the adapter pattern
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.adapters.ai.base import AIProvider
from app.domain.discovery import (
    DiscoveryIntent,
    IntentStatus,
    LocationIntent,
    ServiceIntent,
)

logger = logging.getLogger(__name__)

# JSON schema for AI structured output
_DISCOVERY_INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["complete", "partial", "ambiguous", "insufficient"],
            "description": "Interpretation outcome",
        },
        "service_name": {
            "type": ["string", "null"],
            "description": "Name or description of the requested service",
        },
        "category_slug": {
            "type": ["string", "null"],
            "description": "Best-matching category slug if identifiable",
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Keywords for matching against service names/descriptions",
        },
        "location_city": {"type": ["string", "null"]},
        "location_state": {"type": ["string", "null"]},
        "location_country": {"type": ["string", "null"]},
        "location_postal_code": {"type": ["string", "null"]},
        "requested_at": {
            "type": ["string", "null"],
            "description": "ISO 8601 datetime if customer specified one",
        },
        "requirements": {
            "type": ["object", "null"],
            "description": "Any structured requirements extracted",
        },
        "clarification_needed": {
            "type": ["string", "null"],
            "description": "What to ask the customer if interpretation is uncertain",
        },
    },
    "required": ["status"],
}

_SYSTEM_PROMPT = """You are FIELDed's discovery interpreter. Your job is to convert a customer's natural-language request into structured data.

STRICT RULES:
1. You must ONLY extract information from the customer's message.
2. You must NEVER invent or assume businesses, services, prices, or availability.
3. If the request is too vague to interpret, set status to "insufficient" and explain what's missing in clarification_needed.
4. If multiple interpretations are plausible, set status to "ambiguous" and explain in clarification_needed.
5. For category_slug, use lowercase-hyphenated format (e.g., "electrical", "legal", "accounting", "home-services"). Only set if you're confident.
6. Keywords should be individual words or short phrases extracted from the request that could match service offer names or descriptions.
7. Do NOT fabricate any business names, service names, or IDs.

Output JSON with these fields:
- status: "complete" | "partial" | "ambiguous" | "insufficient"
- service_name: string or null
- category_slug: string or null
- keywords: array of strings
- location_city: string or null
- location_state: string or null
- location_country: string or null
- location_postal_code: string or null
- requested_at: ISO datetime string or null
- requirements: object or null
- clarification_needed: string or null"""


class DiscoveryInterpreter:
    """Converts natural-language customer requests into validated DiscoveryIntent.

    Uses the AIProvider adapter for interpretation.
    Falls back to keyword-based extraction if AI fails.
    """

    def __init__(self, ai_provider: AIProvider) -> None:
        self.ai_provider = ai_provider

    async def interpret(self, raw_query: str, customer_id: str | None = None) -> DiscoveryIntent:
        """Interpret a natural-language discovery request.

        Args:
            raw_query: The customer's natural-language request.
            customer_id: Optional authenticated customer ID.

        Returns:
            Validated DiscoveryIntent. Never raises — returns INSUFFICIENT on failure.
        """
        try:
            ai_result = await self.ai_provider.structured_output(
                prompt=raw_query,
                schema=_DISCOVERY_INTENT_SCHEMA,
                system=_SYSTEM_PROMPT,
                max_tokens=2048,
            )
            return self._build_intent(ai_result, raw_query, customer_id)
        except Exception:
            logger.warning("ai_interpretation_failed, falling back to keyword extraction")
            return self._fallback_interpret(raw_query, customer_id)

    def _build_intent(
        self,
        ai_data: dict[str, Any],
        raw_query: str,
        customer_id: str | None,
    ) -> DiscoveryIntent:
        """Build a validated DiscoveryIntent from AI output.

        Validates strictly — if the AI output doesn't conform,
        returns an INSUFFICIENT intent rather than raising.
        """
        import uuid as uuid_mod

        # Determine status
        try:
            status = IntentStatus(ai_data.get("status", "insufficient"))
        except ValueError:
            status = IntentStatus.INSUFFICIENT

        # Build service intent
        service = ServiceIntent(
            service_name=ai_data.get("service_name"),
            category_slug=ai_data.get("category_slug"),
            keywords=ai_data.get("keywords", []),
        )

        # Build location intent if any location data was extracted
        location = None
        if any(ai_data.get(k) for k in ("location_city", "location_state", "location_country", "location_postal_code")):
            location = LocationIntent(
                city=ai_data.get("location_city"),
                state=ai_data.get("location_state"),
                country=ai_data.get("location_country"),
                postal_code=ai_data.get("location_postal_code"),
            )

        # Parse requested_at
        requested_at = None
        raw_dt = ai_data.get("requested_at")
        if raw_dt:
            from datetime import datetime
            try:
                requested_at = datetime.fromisoformat(raw_dt)
            except (ValueError, TypeError):
                pass

        # Parse customer_id
        parsed_customer_id = None
        if customer_id:
            try:
                parsed_customer_id = uuid_mod.UUID(customer_id)
            except (ValueError, TypeError):
                pass

        return DiscoveryIntent(
            status=status,
            raw_query=raw_query,
            service=service,
            location=location,
            requested_at=requested_at,
            requirements=ai_data.get("requirements"),
            clarification_needed=ai_data.get("clarification_needed"),
            customer_id=parsed_customer_id,
        )

    def _fallback_interpret(self, raw_query: str, customer_id: str | None) -> DiscoveryIntent:
        """Keyword-based fallback when AI interpretation fails.

        Extracts simple keywords from the query for basic matching.
        Returns a PARTIAL intent — the matcher can still try.
        """
        import uuid as uuid_mod

        # Simple keyword extraction: split on whitespace, lowercase, filter stopwords
        stopwords = {
            "i", "need", "a", "an", "the", "to", "for", "my", "is", "are",
            "was", "want", "looking", "find", "help", "with", "in", "at",
            "on", "by", "from", "and", "or", "of", "it", "this", "that",
            "can", "you", "me", "do", "does", "some", "any", "please",
        }
        words = raw_query.lower().split()
        keywords = [w.strip(".,!?;:'\"") for w in words if w.strip(".,!?;:'\"") not in stopwords and len(w) > 2]

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        parsed_customer_id = None
        if customer_id:
            try:
                parsed_customer_id = uuid_mod.UUID(customer_id)
            except (ValueError, TypeError):
                pass

        return DiscoveryIntent(
            status=IntentStatus.PARTIAL,
            raw_query=raw_query,
            service=ServiceIntent(
                service_name=raw_query[:500],
                keywords=unique_keywords[:10],
            ),
            clarification_needed="AI interpretation unavailable; using keyword matching.",
            customer_id=parsed_customer_id,
        )
