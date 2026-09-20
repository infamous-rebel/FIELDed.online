"""Phase 15 — Payment unit tests.

Tests payment state machine transitions, idempotency logic,
provider adapter stub, and service-level business rules
without requiring a database.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.adapters.payment.base import PaymentRequest, RefundRequest
from app.adapters.payment.stub import StubPaymentProvider
from app.domain.common.enums import (
    PAYMENT_TRANSITIONS,
    InvoicePaymentStatus,
    PaymentStatus,
)


class TestPaymentStateMachine:
    """Verify the payment state machine transitions."""

    def test_pending_can_transition_to_processing(self):
        assert PaymentStatus.PROCESSING in PAYMENT_TRANSITIONS[PaymentStatus.PENDING]

    def test_pending_can_transition_to_failed(self):
        assert PaymentStatus.FAILED in PAYMENT_TRANSITIONS[PaymentStatus.PENDING]

    def test_pending_can_transition_to_expired(self):
        assert PaymentStatus.EXPIRED in PAYMENT_TRANSITIONS[PaymentStatus.PENDING]

    def test_pending_can_transition_to_cancelled(self):
        assert PaymentStatus.CANCELLED in PAYMENT_TRANSITIONS[PaymentStatus.PENDING]

    def test_processing_can_transition_to_succeeded(self):
        assert PaymentStatus.SUCCEEDED in PAYMENT_TRANSITIONS[PaymentStatus.PROCESSING]

    def test_processing_can_transition_to_failed(self):
        assert PaymentStatus.FAILED in PAYMENT_TRANSITIONS[PaymentStatus.PROCESSING]

    def test_succeeded_can_transition_to_refunded(self):
        assert PaymentStatus.REFUNDED in PAYMENT_TRANSITIONS[PaymentStatus.SUCCEEDED]

    def test_succeeded_can_transition_to_partially_refunded(self):
        assert PaymentStatus.PARTIALLY_REFUNDED in PAYMENT_TRANSITIONS[PaymentStatus.SUCCEEDED]

    def test_partially_refunded_can_transition_to_refunded(self):
        assert PaymentStatus.REFUNDED in PAYMENT_TRANSITIONS[PaymentStatus.PARTIALLY_REFUNDED]

    def test_failed_is_terminal(self):
        assert PAYMENT_TRANSITIONS[PaymentStatus.FAILED] == set()

    def test_expired_is_terminal(self):
        assert PAYMENT_TRANSITIONS[PaymentStatus.EXPIRED] == set()

    def test_cancelled_is_terminal(self):
        assert PAYMENT_TRANSITIONS[PaymentStatus.CANCELLED] == set()

    def test_refunded_is_terminal(self):
        assert PAYMENT_TRANSITIONS[PaymentStatus.REFUNDED] == set()

    def test_pending_cannot_transition_to_succeeded_directly(self):
        assert PaymentStatus.SUCCEEDED not in PAYMENT_TRANSITIONS[PaymentStatus.PENDING]

    def test_failed_cannot_transition_to_anything(self):
        assert len(PAYMENT_TRANSITIONS[PaymentStatus.FAILED]) == 0

    def test_all_statuses_in_transition_dict(self):
        for status in PaymentStatus:
            assert status in PAYMENT_TRANSITIONS, f"{status} missing from PAYMENT_TRANSITIONS"


class TestStubPaymentProvider:
    """Test the stub payment provider adapter."""

    @pytest.mark.asyncio
    async def test_initiate_payment_returns_success(self):
        provider = StubPaymentProvider()
        request = PaymentRequest(
            amount=Decimal("100.00"),
            currency="GBP",
            description="Test payment",
            idempotency_key="test-key-123",
        )
        result = await provider.initiate_payment(request)
        assert result.success is True
        assert result.provider_reference is not None
        assert result.provider_reference.startswith("stub_pi_")

    @pytest.mark.asyncio
    async def test_initiate_payment_idempotent(self):
        provider = StubPaymentProvider()
        request = PaymentRequest(
            amount=Decimal("100.00"),
            currency="GBP",
            description="Test payment",
            idempotency_key="same-key",
        )
        result1 = await provider.initiate_payment(request)
        result2 = await provider.initiate_payment(request)
        assert result1.provider_reference == result2.provider_reference

    @pytest.mark.asyncio
    async def test_verify_payment_status(self):
        provider = StubPaymentProvider()
        result = await provider.verify_payment_status("stub_pi_test123")
        assert result.success is True
        assert result.raw_response["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_refund_returns_success(self):
        provider = StubPaymentProvider()
        request = RefundRequest(
            provider_payment_reference="stub_pi_test123",
            amount=Decimal("50.00"),
        )
        result = await provider.refund(request)
        assert result.success is True
        assert result.provider_reference.startswith("stub_re_")

    @pytest.mark.asyncio
    async def test_verify_webhook_signature(self):
        provider = StubPaymentProvider()
        result = await provider.verify_webhook_signature(b'{"test": true}', "any-sig", "any-secret")
        assert result is True

    @pytest.mark.asyncio
    async def test_parse_webhook_event(self):
        provider = StubPaymentProvider()
        event = await provider.parse_webhook_event(
            {
                "type": "payment_intent.succeeded",
                "id": "evt_test123",
                "payment_intent": "pi_test123",
                "amount": 10000,
                "currency": "gbp",
                "status": "succeeded",
            }
        )
        assert event.event_type == "payment_intent.succeeded"
        assert event.provider_event_id == "evt_test123"
        assert event.provider_payment_reference == "pi_test123"
        assert event.amount == Decimal("10000")
        assert event.verified is True

    def test_provider_name(self):
        provider = StubPaymentProvider()
        assert provider.provider_name == "stub"


class TestPaymentMethodEnum:
    """Verify payment method enum values."""

    def test_card_exists(self):
        from app.domain.common.enums import PaymentMethod

        assert PaymentMethod.CARD == "card"

    def test_bank_transfer_exists(self):
        from app.domain.common.enums import PaymentMethod

        assert PaymentMethod.BANK_TRANSFER == "bank_transfer"

    def test_cash_exists(self):
        from app.domain.common.enums import PaymentMethod

        assert PaymentMethod.CASH == "cash"


class TestInvoicePaymentStatusExtended:
    """Verify the extended invoice payment status enum."""

    def test_failed_status_exists(self):
        assert InvoicePaymentStatus.FAILED == "failed"

    def test_refunded_status_exists(self):
        assert InvoicePaymentStatus.REFUNDED == "refunded"

    def test_partially_refunded_status_exists(self):
        assert InvoicePaymentStatus.PARTIALLY_REFUNDED == "partially_refunded"


class TestPaymentWebhookStatus:
    """Verify payment webhook status enum."""

    def test_received(self):
        from app.domain.common.enums import PaymentWebhookStatus

        assert PaymentWebhookStatus.RECEIVED == "RECEIVED"

    def test_processed(self):
        from app.domain.common.enums import PaymentWebhookStatus

        assert PaymentWebhookStatus.PROCESSED == "PROCESSED"


class TestPaymentAuditEvents:
    """Verify payment audit event types exist."""

    def test_payment_initiated(self):
        from app.domain.common.enums import AuditEventType

        assert AuditEventType.PAYMENT_INITIATED == "PAYMENT_INITIATED"

    def test_payment_succeeded(self):
        from app.domain.common.enums import AuditEventType

        assert AuditEventType.PAYMENT_SUCCEEDED == "PAYMENT_SUCCEEDED"

    def test_payment_refunded(self):
        from app.domain.common.enums import AuditEventType

        assert AuditEventType.PAYMENT_REFUNDED == "PAYMENT_REFUNDED"

    def test_invoice_balance_updated(self):
        from app.domain.common.enums import AuditEventType

        assert AuditEventType.INVOICE_BALANCE_UPDATED == "INVOICE_BALANCE_UPDATED"
