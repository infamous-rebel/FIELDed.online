"""Push notification provider abstract base class.

Defines the interface for push notification delivery.
Domain services depend on this interface — never on a concrete SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.adapters.common import ProviderResult


@dataclass
class PushMessage:
    """A push notification to be sent."""

    device_token: str
    title: str
    body: str
    data: dict = field(default_factory=dict)


class PushProvider(ABC):
    """Abstract base class for push notification providers."""

    @abstractmethod
    async def send(self, message: PushMessage) -> ProviderResult:
        """Send a push notification.

        Returns:
            ProviderResult with provider_reference on success.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this push provider."""
        ...
