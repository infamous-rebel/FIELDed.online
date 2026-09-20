"""Stub payment provider for development and testing.

Returns deterministic results without contacting any external
payment service.  Used when PAYMENT_PROVIDER=mock/stub.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from app.adapters.common import ProviderResult
from app.adapters.payment.base import (
    PaymentProvider,
    PaymentRequest,
    RefundRequest,
    WebhookEvent,
)


class StubPaymentProvider(PaymentProvider):
    """Deterministic stub for payment processing.

    Always returns success for valid-looking requests.
    Useful for integration tests and local development.
    """

    @property
    def provider_name(self) -> str:
        return "stub"

    async def initiate_payment(self, request: PaymentRequest) -> ProviderResult:
        """Simulate payment initiation."""
        # Generate a deterministic provider reference from idempotency key
        ref = f"stub_pi_{hashlib.sha256(request.idempotency_key.encode()).hexdigest()[:24]}"
        return ProviderResult.ok(
            provider_reference=ref,
            raw_response={
                "status": "succeeded",
                "amount": str(request.amount),
                "currency": request.currency,
            },
        )

    async def verify_payment_status(
        self, provider_payment_reference: str
    ) -> ProviderResult:
        """Simulate status verification — always returns succeeded."""
        return ProviderResult.ok(
            provider_reference=provider_payment_reference,
            raw_response={"status": "succeeded"},
        )

    async def refund(self, request: RefundRequest) -> ProviderResult:
        """Simulate refund processing."""
        refund_ref = f"stub_re_{uuid.uuid4().hex[:24]}"
        return ProviderResult.ok(
            provider_reference=refund_ref,
            raw_response={
                "status": "succeeded",
                "amount": str(request.amount) if request.amount else "full",
            },
        )

    async def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """Stub always returns True (no real signature to verify)."""
        return True

    async def parse_webhook_event(self, payload: dict) -> WebhookEvent:
        """Parse a stub webhook event."""
        return WebhookEvent(
            event_type=payload.get("type", "payment_intent.succeeded"),
            provider_event_id=payload.get("id", f"evt_{uuid.uuid4().hex[:16]}"),
            provider_payment_reference=payload.get("payment_intent", f"stub_pi_{uuid.uuid4().hex[:24]}"),
            amount=Decimal(str(payload["amount"])) if "amount" in payload else None,
            currency=payload.get("currency"),
            status=payload.get("status", "succeeded"),
            raw_payload=payload,
            verified=True,
        )
