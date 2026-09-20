"""Common provider contract.

All provider adapters return a ProviderResult dataclass.
This ensures domain services depend on a uniform interface,
never on provider-specific response shapes.

Provider SDK exceptions are translated into ProviderResult
inside each adapter — they never propagate to domain code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderResult:
    """Unified result from any provider adapter.

    Attributes:
        success: Whether the provider operation succeeded.
        provider_reference: External provider identifier
            (e.g. Resend message ID, Twilio SID).  None on failure.
        error: Human-readable error description.  None on success.
        retryable: Whether the operation may succeed if retried.
        raw_response: Optional provider-specific response metadata
            for audit/debugging.  Not used for domain logic.
    """

    success: bool
    provider_reference: str | None = None
    error: str | None = None
    retryable: bool = False
    raw_response: dict = field(default_factory=dict)

    @classmethod
    def ok(cls, provider_reference: str, **kwargs: object) -> ProviderResult:
        """Create a successful result."""
        return cls(
            success=True,
            provider_reference=provider_reference,
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def failure(
        cls,
        error: str,
        *,
        retryable: bool = False,
        raw_response: dict | None = None,
    ) -> ProviderResult:
        """Create a failure result."""
        return cls(
            success=False,
            error=error,
            retryable=retryable,
            raw_response=raw_response or {},
        )
