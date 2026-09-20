"""Email provider abstract base class.

Defines the interface for email sending integrations.
Concrete implementations can wrap Resend, SendGrid, SES, etc.

Domain services depend on this interface — never on a concrete SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.adapters.common import ProviderResult


@dataclass
class EmailMessage:
    """An email message to be sent."""

    to: str | list[str]
    subject: str
    body: str
    from_address: str = ""
    html_body: str | None = None
    reply_to: str | None = None
    attachments: list[dict[str, str]] = field(default_factory=list)


class EmailProvider(ABC):
    """Abstract base class for email providers.

    The communication domain creates EmailMessage objects.
    The adapter sends them through the configured provider.
    All results are returned as ProviderResult.
    """

    @abstractmethod
    async def send(self, message: EmailMessage) -> ProviderResult:
        """Send an email message.

        Args:
            message: The email message to send.

        Returns:
            ProviderResult with provider_reference set to the
            provider's message ID on success.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this email provider."""
        ...
