"""Voice provider abstract base class.

Defines the interface for outbound voice call initiation.
Phase 14A supports real outbound call initiation only.
The conversational Call Agent belongs to Phase 14B.

Domain services depend on this interface — never on a concrete SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.adapters.common import ProviderResult


@dataclass
class VoiceCallRequest:
    """Request to initiate an outbound voice call."""

    to: str  # Phone number in E.164 format
    from_number: str
    callback_url: str | None = None
    callback_method: str = "POST"
    metadata: dict = field(default_factory=dict)


@dataclass
class VoiceCallResult:
    """Result of a voice call initiation.

    Wraps ProviderResult for voice-specific typing.
    """

    success: bool
    provider_reference: str | None = None
    error: str | None = None
    retryable: bool = False
    raw_response: dict = field(default_factory=dict)

    @classmethod
    def from_provider_result(cls, result: ProviderResult) -> VoiceCallResult:
        """Create from a ProviderResult."""
        return cls(
            success=result.success,
            provider_reference=result.provider_reference,
            error=result.error,
            retryable=result.retryable,
            raw_response=result.raw_response,
        )


class VoiceProvider(ABC):
    """Abstract base class for voice call providers.

    Phase 14A: outbound call initiation only.
    """

    @abstractmethod
    async def initiate_call(self, request: VoiceCallRequest) -> ProviderResult:
        """Initiate an outbound voice call.

        Returns:
            ProviderResult with provider_reference set to the
            call SID on success.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this voice provider."""
        ...
