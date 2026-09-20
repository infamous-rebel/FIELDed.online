"""AI provider abstract base class.

Defines the interface for AI/LLM integrations.
Concrete implementations can wrap Gemini, Groq, OpenAI, or any other provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AIResponse:
    """Structured response from an AI provider."""
    content: str
    model: str
    usage: dict[str, int] | None = None
    raw: dict[str, Any] | None = None


class AIProvider(ABC):
    """Abstract base class for AI/LLM providers.

    All AI interactions go through this interface.
    The core domain never calls a specific provider directly.
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AIResponse:
        """Generate a text completion.

        Args:
            prompt: The user prompt.
            system: Optional system instruction.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            Structured AI response.
        """
        ...

    @abstractmethod
    async def structured_output(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate a structured output conforming to a JSON schema.

        Args:
            prompt: The user prompt.
            schema: JSON schema for the expected output.
            system: Optional system instruction.
            max_tokens: Maximum tokens in the response.

        Returns:
            Parsed structured data matching the schema.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this AI provider."""
        ...
