"""SMS provider abstract base class.

Defines the interface for SMS sending integrations.
Concrete implementations can wrap Twilio, Vonage, SNS, etc.

Domain services depend on this interface — never on a concrete SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.adapters.common import ProviderResult


@dataclass
class SMSMessage:
    """An SMS message to be sent."""

    to: str
    body: str
    from_number: str = ""


class SMSProvider(ABC):
    """Abstract base class for SMS providers."""

    @abstractmethod
    async def send(self, message: SMSMessage) -> ProviderResult:
        """Send an SMS message.

        Args:
            message: The SMS message to send.

        Returns:
            ProviderResult with provider_reference set to the
            provider's message SID on success.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this SMS provider."""
        ...
