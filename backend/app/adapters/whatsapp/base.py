"""WhatsApp provider abstract base class.

Defines the interface for WhatsApp message sending.
Domain services depend on this interface — never on a concrete SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.adapters.common import ProviderResult


@dataclass
class WhatsAppMessage:
    """A WhatsApp message to be sent."""

    to: str  # Phone number in E.164 format
    body: str
    template_name: str | None = None
    template_language: str | None = None
    template_components: list[dict] | None = None


class WhatsAppProvider(ABC):
    """Abstract base class for WhatsApp providers."""

    @abstractmethod
    async def send(self, message: WhatsAppMessage) -> ProviderResult:
        """Send a WhatsApp message.

        Returns:
            ProviderResult with provider_reference on success.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this WhatsApp provider."""
        ...
