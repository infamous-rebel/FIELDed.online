"""Stub AI provider for development and testing.

Provides a deterministic keyword-based interpretation when no real
AI provider is configured. This allows the discovery system to work
end-to-end without external AI dependencies.
"""

from __future__ import annotations

import re
from typing import Any

from app.adapters.ai.base import AIProvider, AIResponse


class StubAIProvider(AIProvider):
    """Deterministic stub AI provider for development/testing.

    Extracts keywords from the prompt and returns structured output
    matching the discovery intent schema.
    """

    @property
    def provider_name(self) -> str:
        return "stub"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AIResponse:
        return AIResponse(
            content="Stub provider — use structured_output for discovery.",
            model="stub-v1",
        )

    async def structured_output(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Extract structured intent from the prompt using keyword analysis."""
        text = prompt.lower().strip()

        # Simple keyword extraction
        stopwords = {
            "i",
            "need",
            "a",
            "an",
            "the",
            "to",
            "for",
            "my",
            "is",
            "are",
            "was",
            "want",
            "looking",
            "find",
            "help",
            "with",
            "in",
            "at",
            "on",
            "by",
            "from",
            "and",
            "or",
            "of",
            "it",
            "this",
            "that",
            "can",
            "you",
            "me",
            "do",
            "does",
            "some",
            "any",
            "please",
            "someone",
            "who",
            "what",
            "where",
            "when",
            "how",
            "much",
        }
        words = text.split()
        keywords = [
            w.strip(".,!?;:'\"()[]{}")
            for w in words
            if w.strip(".,!?;:'\"()[]{}") not in stopwords and len(w.strip(".,!?;:'\"()[]{}")) > 2
        ]
        # Deduplicate
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        # Try to detect category from common terms
        category_map = {
            "electric": "electrical",
            "electrician": "electrical",
            "wiring": "electrical",
            "plumb": "plumbing",
            "plumber": "plumbing",
            "legal": "legal",
            "lawyer": "legal",
            "contract": "legal",
            "account": "accounting",
            "accountant": "accounting",
            "tax": "accounting",
            "clean": "cleaning",
            "cleaning": "cleaning",
            "paint": "painting",
            "painter": "painting",
            "repair": "repair",
            "inspect": "inspection",
            "inspection": "inspection",
        }
        category_slug = None
        for word in keywords:
            for trigger, slug in category_map.items():
                if trigger in word:
                    category_slug = slug
                    break
            if category_slug:
                break

        # Try to detect location
        location_city = None
        location_state = None
        # Very basic: look for "in <CityName>" pattern
        in_match = re.search(r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", prompt)
        if in_match:
            location_city = in_match.group(1)

        # Determine status
        if not keywords and not category_slug:
            status = "insufficient"
            clarification = "Please describe what service you need."
        elif not category_slug and len(keywords) < 2:
            status = "partial"
            clarification = "Try being more specific about the service you need."
        else:
            status = "complete"
            clarification = None

        return {
            "status": status,
            "service_name": prompt[:500],
            "category_slug": category_slug,
            "keywords": unique[:10],
            "location_city": location_city,
            "location_state": location_state,
            "location_country": None,
            "location_postal_code": None,
            "requested_at": None,
            "requirements": None,
            "clarification_needed": clarification,
        }
