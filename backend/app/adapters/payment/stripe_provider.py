"""Stripe payment provider adapter.

Implements the PaymentProvider interface using Stripe's official SDK.
Uses StripeClient (v1 namespace) for PaymentIntent creation/retrieval,
refunds, and webhook signature verification.

Stripe test mode:
    Set PAYMENT_API_KEY to a key starting with ``sk_test_``.
    All transactions will use Stripe's sandbox — no real money moves.

Stripe live mode:
    Set PAYMENT_API_KEY to a key starting with ``sk_live_``.
    Real charges will be processed.  Ensure PAYMENT_WEBHOOK_SECRET is
    configured and the webhook endpoint is registered in the Stripe
    dashboard.

Domain code depends only on the PaymentProvider ABC — never on this
module directly.  All Stripe SDK exceptions are translated into
ProviderResult inside this adapter.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
import stripe
from stripe import StripeClient

from app.adapters.common import ProviderResult
from app.adapters.payment.base import (
    PaymentProvider,
    PaymentRequest,
    RefundRequest,
    WebhookEvent,
)

logger = logging.getLogger(__name__)

# Stripe status → FIELDed PaymentStatus mapping
_STRIPE_TO_PAYMENT_STATUS: dict[str, str] = {
    "requires_payment_method": "pending",
    "requires_confirmation": "pending",
    "requires_action": "processing",
    "processing": "processing",
    "succeeded": "succeeded",
    "canceled": "cancelled",
    "incomplete": "pending",
    "incomplete_expired": "expired",
}

# Stripe refund status → FIELDed RefundStatus mapping
_STRIPE_REFUND_STATUS: dict[str, str] = {
    "succeeded": "succeeded",
    "pending": "processing",
    "requires_action": "processing",
    "failed": "failed",
    "canceled": "failed",
}


def _amount_to_stripe(amount: Decimal, currency: str) -> int:
    """Convert a decimal amount to Stripe's smallest currency unit.

    Stripe expects amounts in pence/cents for most currencies.
    Zero-decimal currencies (e.g. JPY) use the amount directly.
    """
    zero_decimal_currencies = {"jpy", "krw", "vnd", "clp", "huf"}
    if currency.lower() in zero_decimal_currencies:
        return int(amount)
    return int(amount * 100)


def _amount_from_stripe(amount: int, currency: str) -> Decimal:
    """Convert Stripe's smallest currency unit back to decimal."""
    zero_decimal_currencies = {"jpy", "krw", "vnd", "clp", "huf"}
    if currency.lower() in zero_decimal_currencies:
        return Decimal(str(amount))
    return Decimal(str(amount)) / Decimal("100")


class StripePaymentProvider(PaymentProvider):
    """Stripe payment provider using StripeClient.

    Accepts an optional ``http_client`` parameter for test injection.
    In production, Stripe SDK's default HTTP client is used.
    """

    def __init__(
        self,
        api_key: str,
        webhook_secret: str = "",
        *,
        http_client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._webhook_secret = webhook_secret

        client_kwargs: dict[str, Any] = {}
        if http_client is not None:
            client_kwargs["http_client"] = http_client

        self._client = StripeClient(api_key=api_key, **client_kwargs)

    @property
    def provider_name(self) -> str:
        return "stripe"

    # --- Payment initiation ---

    async def initiate_payment(self, request: PaymentRequest) -> ProviderResult:
        """Create a Stripe PaymentIntent.

        Returns the PaymentIntent ID as provider_reference.
        The client_secret is included in raw_response for the frontend
        to confirm the payment client-side.
        """
        try:
            amount_minor = _amount_to_stripe(request.amount, request.currency)

            params: dict[str, Any] = {
                "amount": amount_minor,
                "currency": request.currency.lower(),
                "description": request.description,
                "metadata": {
                    "fielded_idempotency_key": request.idempotency_key,
                    **request.metadata,
                },
            }

            # Set idempotency key so Stripe deduplicates at their end too
            options: dict[str, Any] = {
                "idempotency_key": request.idempotency_key,
            }

            if request.customer_email:
                # Create or retrieve customer for receipt emails
                params["receipt_email"] = request.customer_email

            if request.return_url:
                params["automatic_payment_methods"] = {"enabled": True}

            pi = self._client.v1.payment_intents.create(params, options)

            return ProviderResult.ok(
                provider_reference=pi.id,
                raw_response={
                    "status": pi.status,
                    "client_secret": getattr(pi, "client_secret", ""),
                    "amount": str(_amount_from_stripe(pi.amount, pi.currency)),
                    "currency": pi.currency,
                    "id": pi.id,
                },
            )

        except stripe.StripeError as exc:
            logger.warning("stripe_initiate_payment_failed: %s", exc)
            return ProviderResult.failure(
                error=str(getattr(exc, "user_message", str(exc))),
                retryable=_is_retryable_stripe_error(exc),
                raw_response={"stripe_error": str(exc), "code": getattr(exc, "code", None)},
            )
        except Exception as exc:
            logger.exception("stripe_initiate_payment_unexpected_error")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )

    # --- Status verification ---

    async def verify_payment_status(
        self, provider_payment_reference: str
    ) -> ProviderResult:
        """Retrieve a PaymentIntent and return its current status."""
        try:
            pi = self._client.v1.payment_intents.retrieve(provider_payment_reference)
            mapped_status = _STRIPE_TO_PAYMENT_STATUS.get(pi.status, pi.status)

            return ProviderResult.ok(
                provider_reference=pi.id,
                raw_response={
                    "status": mapped_status,
                    "stripe_status": pi.status,
                    "amount": str(_amount_from_stripe(pi.amount, pi.currency)),
                    "currency": pi.currency,
                },
            )

        except stripe.StripeError as exc:
            logger.warning("stripe_verify_status_failed: %s", exc)
            return ProviderResult.failure(
                error=str(getattr(exc, "user_message", str(exc))),
                retryable=_is_retryable_stripe_error(exc),
            )
        except Exception as exc:
            logger.exception("stripe_verify_status_unexpected_error")
            return ProviderResult.failure(error=f"Unexpected error: {exc}", retryable=False)

    # --- Refunds ---

    async def refund(self, request: RefundRequest) -> ProviderResult:
        """Create a Stripe Refund against a PaymentIntent.

        If amount is None, Stripe processes a full refund automatically.
        """
        try:
            params: dict[str, Any] = {
                "payment_intent": request.provider_payment_reference,
            }

            if request.amount is not None:
                # Determine currency from the original PaymentIntent
                pi = self._client.v1.payment_intents.retrieve(
                    request.provider_payment_reference
                )
                params["amount"] = _amount_to_stripe(request.amount, pi.currency)

            if request.reason:
                params["reason"] = "requested_by_customer"
                params["metadata"] = {"reason": request.reason}

            options: dict[str, Any] = {}
            if request.idempotency_key:
                options["idempotency_key"] = request.idempotency_key

            refund_obj = self._client.v1.refunds.create(params, options)

            refund_status = _STRIPE_REFUND_STATUS.get(
                refund_obj.status, refund_obj.status
            )

            return ProviderResult.ok(
                provider_reference=refund_obj.id,
                raw_response={
                    "status": refund_status,
                    "stripe_status": refund_obj.status,
                    "amount": str(
                        _amount_from_stripe(
                            getattr(refund_obj, "amount", 0),
                            getattr(refund_obj, "currency", "gbp"),
                        )
                    ),
                    "id": refund_obj.id,
                },
            )

        except stripe.StripeError as exc:
            logger.warning("stripe_refund_failed: %s", exc)
            return ProviderResult.failure(
                error=str(getattr(exc, "user_message", str(exc))),
                retryable=_is_retryable_stripe_error(exc),
                raw_response={"stripe_error": str(exc), "code": getattr(exc, "code", None)},
            )
        except Exception as exc:
            logger.exception("stripe_refund_unexpected_error")
            return ProviderResult.failure(error=f"Unexpected error: {exc}", retryable=False)

    # --- Webhook verification ---

    async def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """Verify a Stripe webhook signature.

        Uses stripe.WebhookSignature.verify_header which checks the
        HMAC-SHA256 signature against the webhook endpoint secret.
        """
        try:
            stripe.WebhookSignature.verify_header(
                payload=payload,
                header=signature,
                secret=secret,
            )
            return True
        except stripe.SignatureVerificationError as exc:
            logger.warning("stripe_webhook_signature_invalid: %s", exc)
            return False
        except Exception:
            logger.exception("stripe_webhook_signature_unexpected_error")
            return False

    # --- Webhook parsing ---

    async def parse_webhook_event(self, payload: dict) -> WebhookEvent:
        """Parse a Stripe webhook event payload into a WebhookEvent.

        The payload should already be signature-verified.
        Maps Stripe event types to FIELDed webhook semantics.
        """
        event_type = payload.get("type", "")
        event_id = payload.get("id", "")
        data_object = payload.get("data", {}).get("object", {})

        # Extract PaymentIntent reference from the event data
        provider_payment_ref = ""
        amount = None
        currency = None
        status = None

        if event_type.startswith("payment_intent."):
            provider_payment_ref = data_object.get("id", "")
            if "amount" in data_object:
                amount = _amount_from_stripe(
                    data_object["amount"],
                    data_object.get("currency", "gbp"),
                )
            currency = data_object.get("currency")
            status = _STRIPE_TO_PAYMENT_STATUS.get(
                data_object.get("status", ""), data_object.get("status", "")
            )

        elif event_type.startswith("charge.refund"):
            # Refund events — extract the PaymentIntent from the charge
            charge_ref = data_object.get("payment_intent", "")
            provider_payment_ref = charge_ref
            if "amount" in data_object:
                amount = _amount_from_stripe(
                    data_object["amount"],
                    data_object.get("currency", "gbp"),
                )
            currency = data_object.get("currency")
            status = "refunded"

        return WebhookEvent(
            event_type=event_type,
            provider_event_id=event_id,
            provider_payment_reference=provider_payment_ref,
            amount=amount,
            currency=currency,
            status=status,
            raw_payload=payload,
            verified=True,
        )


def _is_retryable_stripe_error(exc: stripe.StripeError) -> bool:
    """Determine if a Stripe error is retryable.

    Rate limits, connection errors, and API connection issues are
    retryable.  Card declines and invalid requests are not.
    """
    if isinstance(exc, stripe.RateLimitError):
        return True
    if isinstance(exc, stripe.APIConnectionError):
        return True
    if isinstance(exc, stripe.APIError):
        return True
    if isinstance(exc, stripe.IdempotencyError):
        return True
    # Card errors, invalid requests, etc. are not retryable
    return False
