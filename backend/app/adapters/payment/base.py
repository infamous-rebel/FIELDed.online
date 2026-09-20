"""Payment provider abstract base class.

Defines the interface for payment processing integrations.
Concrete implementations can wrap Stripe, PayPal, Square, etc.

FIELDed selects Stripe as the default payment provider based on:
- Market dominance in online payments (UK + global)
- Full support for cards, digital wallets (Apple/Google Pay),
  bank transfers, and multi-currency (GBP primary)
- Robust webhook system with signature verification
- Idempotent API with built-in idempotency key support
- PCI-DSS Level 1 compliance (no card data touches our servers)

Domain services depend on this interface — never on a concrete SDK.
All provider SDK exceptions are translated into ProviderResult
inside the adapter — they never propagate to domain code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from app.adapters.common import ProviderResult


@dataclass
class PaymentRequest:
    """Request to initiate a payment."""

    amount: Decimal
    currency: str  # ISO 4217 (e.g. GBP, USD, EUR)
    description: str
    idempotency_key: str
    customer_email: str | None = None
    customer_reference: str | None = None
    metadata: dict = field(default_factory=dict)
    # Optional: return URL for redirect-based flows
    return_url: str | None = None
    # Optional: specific payment method type
    payment_method: str | None = None


@dataclass
class RefundRequest:
    """Request to refund a payment."""

    provider_payment_reference: str
    amount: Decimal | None = None  # None = full refund
    reason: str | None = None
    idempotency_key: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """A parsed webhook event from the payment provider."""

    event_type: str  # e.g. "payment_intent.succeeded"
    provider_event_id: str
    provider_payment_reference: str
    amount: Decimal | None = None
    currency: str | None = None
    status: str | None = None  # Provider-specific status
    raw_payload: dict = field(default_factory=dict)
    verified: bool = False


class PaymentProvider(ABC):
    """Abstract base class for payment providers.

    The payment domain creates PaymentRequest objects.
    The adapter processes them through the configured provider.
    All results are returned as ProviderResult.
    """

    @abstractmethod
    async def initiate_payment(self, request: PaymentRequest) -> ProviderResult:
        """Initiate a payment with the provider.

        Returns:
            ProviderResult with provider_reference set to the
            provider's payment/transaction ID on success.
        """
        ...

    @abstractmethod
    async def verify_payment_status(
        self, provider_payment_reference: str
    ) -> ProviderResult:
        """Verify the current status of a payment.

        Returns:
            ProviderResult with success=True and raw_response
            containing the current status on success.
        """
        ...

    @abstractmethod
    async def refund(self, request: RefundRequest) -> ProviderResult:
        """Process a refund for a completed payment.

        Returns:
            ProviderResult with provider_reference set to the
            refund ID on success.
        """
        ...

    @abstractmethod
    async def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """Verify a webhook signature from the provider.

        Returns:
            True if the signature is valid, False otherwise.
        """
        ...

    @abstractmethod
    async def parse_webhook_event(self, payload: dict) -> WebhookEvent:
        """Parse a raw webhook payload into a structured event.

        The payload should already be signature-verified.

        Returns:
            WebhookEvent with parsed fields.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this payment provider."""
        ...
