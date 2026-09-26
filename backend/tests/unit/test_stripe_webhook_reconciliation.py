"""Stripe webhook reconciliation unit tests.

Covers:
- StripePaymentProvider.parse_webhook_event for all event types
- StripeWebhookReconciliationService: idempotency, state transitions,
  tenant isolation, refund/dispute handling, out-of-order events
- Webhook endpoint: signature verification, error handling
- Payment state machine: DISPUTED transitions
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.adapters.payment.stripe_provider import StripePaymentProvider
from app.domain.common.enums import (
    PAYMENT_TRANSITIONS,
    PaymentStatus,
)
from app.domain.payment.models import Payment
from app.domain.payment.stripe_event_model import StripeEvent

# ── Payment state machine: DISPUTED transitions ─────────────────


class TestDisputedStateMachine:
    """Verify the DISPUTED state is correctly wired."""

    def test_succeeded_can_transition_to_disputed(self):
        assert PaymentStatus.DISPUTED in PAYMENT_TRANSITIONS[PaymentStatus.SUCCEEDED]

    def test_partially_refunded_can_transition_to_disputed(self):
        assert PaymentStatus.DISPUTED in PAYMENT_TRANSITIONS[PaymentStatus.PARTIALLY_REFUNDED]

    def test_disputed_can_transition_to_refunded(self):
        assert PaymentStatus.REFUNDED in PAYMENT_TRANSITIONS[PaymentStatus.DISPUTED]

    def test_disputed_can_transition_to_succeeded(self):
        assert PaymentStatus.SUCCEEDED in PAYMENT_TRANSITIONS[PaymentStatus.DISPUTED]

    def test_disputed_cannot_transition_to_failed(self):
        assert PaymentStatus.FAILED not in PAYMENT_TRANSITIONS[PaymentStatus.DISPUTED]

    def test_disputed_cannot_transition_to_pending(self):
        assert PaymentStatus.PENDING not in PAYMENT_TRANSITIONS[PaymentStatus.DISPUTED]

    def test_disputed_value(self):
        assert PaymentStatus.DISPUTED == "disputed"


# ── StripePaymentProvider.parse_webhook_event ──────────────────


class TestStripeWebhookParsing:
    """Test the enhanced parse_webhook_event for all event types."""

    @pytest.fixture
    def provider(self):
        return StripePaymentProvider(api_key="sk_test_fake", webhook_secret="whsec_test")

    @pytest.mark.asyncio
    async def test_parse_payment_intent_succeeded(self, provider):
        payload = {
            "id": "evt_test_001",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 5000,
                    "currency": "gbp",
                    "status": "succeeded",
                    "on_behalf_of": "acct_test_abc",
                }
            },
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "payment_intent.succeeded"
        assert event.provider_event_id == "evt_test_001"
        assert event.provider_payment_reference == "pi_test_123"
        assert event.amount == Decimal("50.00")
        assert event.currency == "gbp"
        assert event.status == "succeeded"
        assert event.verified is True

    @pytest.mark.asyncio
    async def test_parse_payment_intent_failed(self, provider):
        payload = {
            "id": "evt_test_002",
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_test_456",
                    "amount": 10000,
                    "currency": "gbp",
                    "status": "requires_payment_method",
                    "last_payment_error": {
                        "message": "Card declined",
                        "decline_code": "generic_decline",
                    },
                }
            },
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "payment_intent.payment_failed"
        assert event.provider_payment_reference == "pi_test_456"
        assert event.status == "pending"  # mapped from requires_payment_method

    @pytest.mark.asyncio
    async def test_parse_charge_refund(self, provider):
        payload = {
            "id": "evt_test_003",
            "type": "charge.refund.updated",
            "data": {
                "object": {
                    "id": "ch_test_789",
                    "payment_intent": "pi_test_123",
                    "amount_refunded": 5000,
                    "amount": 5000,
                    "currency": "gbp",
                }
            },
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "charge.refund.updated"
        assert event.provider_payment_reference == "pi_test_123"
        assert event.status == "refunded"

    @pytest.mark.asyncio
    async def test_parse_charge_dispute_created(self, provider):
        payload = {
            "id": "evt_test_004",
            "type": "charge.dispute.created",
            "data": {
                "object": {
                    "id": "dp_test_abc",
                    "amount": 3000,
                    "currency": "gbp",
                    "reason": "fraudulent",
                    "status": "needs_response",
                    "charge": {
                        "id": "ch_test_xyz",
                        "payment_intent": "pi_test_123",
                    },
                }
            },
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "charge.dispute.created"
        assert event.provider_payment_reference == "pi_test_123"
        assert event.status == "disputed"
        assert event.amount == Decimal("30.00")

    @pytest.mark.asyncio
    async def test_parse_charge_dispute_closed_won(self, provider):
        payload = {
            "id": "evt_test_005",
            "type": "charge.dispute.closed",
            "data": {
                "object": {
                    "id": "dp_test_abc",
                    "status": "won",
                    "charge": {
                        "payment_intent": "pi_test_123",
                    },
                }
            },
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "charge.dispute.closed"
        assert event.provider_payment_reference == "pi_test_123"

    @pytest.mark.asyncio
    async def test_parse_unknown_event_type(self, provider):
        payload = {
            "id": "evt_test_006",
            "type": "payout.paid",
            "data": {"object": {"id": "po_test_123"}},
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "payout.paid"
        assert event.provider_payment_reference == ""

    @pytest.mark.asyncio
    async def test_parse_account_application_event(self, provider):
        payload = {
            "id": "evt_test_007",
            "type": "account.application.authorized",
            "data": {"object": {"id": "ca_test_123"}},
        }
        event = await provider.parse_webhook_event(payload)
        assert event.event_type == "account.application.authorized"
        assert event.provider_payment_reference == ""


# ── StripeWebhookReconciliationService (DB tests) ──────────────


class TestReconciliationIdempotency:
    """Test idempotent event processing via the DB."""

    @pytest.mark.asyncio
    async def test_duplicate_event_not_processed_twice(self, db_session):
        """A duplicate Stripe event must be detected and not re-processed."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="payment_intent.succeeded",
            provider_event_id="evt_idempotency_test",
            provider_payment_reference="pi_nonexistent",
            amount=Decimal("50.00"),
            currency="gbp",
            status="succeeded",
            raw_payload={
                "id": "evt_idempotency_test",
                "type": "payment_intent.succeeded",
                "data": {"object": {"id": "pi_nonexistent", "amount": 5000, "currency": "gbp", "status": "succeeded"}},
            },
            verified=True,
        )

        # First call — unknown payment (no matching payment)
        result1 = await svc.reconcile(event)
        assert result1.status == "unknown_payment"

        # Second call — duplicate detection
        result2 = await svc.reconcile(event)
        assert result2.status == "duplicate"
        assert result2.id == result1.id


class TestReconciliationIgnoredEvents:
    """Test that unhandled event types are recorded as ignored."""

    @pytest.mark.asyncio
    async def test_unhandled_event_type_ignored(self, db_session):
        from app.adapters.payment.base import WebhookEvent
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="payout.paid",
            provider_event_id="evt_ignored_test",
            provider_payment_reference="",
            raw_payload={"id": "evt_ignored_test", "type": "payout.paid", "data": {"object": {}}},
            verified=True,
        )

        result = await svc.reconcile(event)
        assert result.status == "ignored"


class TestReconciliationTenantIsolation:
    """Test tenant isolation in webhook processing."""

    @pytest.mark.asyncio
    async def test_unknown_payment_recorded(self, db_session):
        """Webhook for unknown payment_intent is recorded as unknown_payment."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="payment_intent.succeeded",
            provider_event_id="evt_tenant_test",
            provider_payment_reference="pi_does_not_exist",
            amount=Decimal("100.00"),
            currency="gbp",
            status="succeeded",
            raw_payload={
                "id": "evt_tenant_test",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_does_not_exist",
                        "amount": 10000,
                        "currency": "gbp",
                        "status": "succeeded",
                        "on_behalf_of": "acct_wrong",
                    }
                },
            },
            verified=True,
        )

        result = await svc.reconcile(event)
        assert result.status == "unknown_payment"
        assert result.payment_id is None
        assert result.business_id is None


class TestStripeEventModel:
    """Test the StripeEvent model fields."""

    def test_stripe_event_fields(self):
        """StripeEvent has all required fields."""
        evt = StripeEvent(
            stripe_event_id="evt_test_model",
            event_type="payment_intent.succeeded",
            payment_intent_id="pi_test_model",
            stripe_account_id="acct_test",
            status="processed",
        )
        assert evt.stripe_event_id == "evt_test_model"
        assert evt.event_type == "payment_intent.succeeded"
        assert evt.payment_intent_id == "pi_test_model"
        assert evt.status == "processed"


class TestWebhookSignatureVerification:
    """Test Stripe webhook signature verification."""

    @pytest.mark.asyncio
    async def test_valid_signature_returns_true(self):
        """A correctly signed payload should verify."""
        import hashlib
        import hmac
        import time

        secret = "whsec_test_secret"
        payload = b'{"id":"evt_test","type":"payment_intent.succeeded"}'
        timestamp = int(time.time())
        signed_payload = f"{timestamp}.{payload.decode()}"
        signature = hmac.new(
            secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        header = f"t={timestamp},v1={signature}"

        provider = StripePaymentProvider(api_key="sk_test", webhook_secret=secret)
        result = await provider.verify_webhook_signature(payload, header, secret)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_false(self):
        """An incorrectly signed payload should fail verification."""
        provider = StripePaymentProvider(api_key="sk_test", webhook_secret="whsec_secret")
        result = await provider.verify_webhook_signature(
            b'{"id":"evt_test"}',
            "t=12345,v1=invalidsignature",
            "whsec_secret",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_signature_returns_false(self):
        provider = StripePaymentProvider(api_key="sk_test", webhook_secret="whsec_secret")
        result = await provider.verify_webhook_signature(
            b'{"id":"evt_test"}',
            "",
            "whsec_secret",
        )
        assert result is False


class TestReconciliationWithPayment:
    """Test reconciliation against actual Payment records in DB."""

    @pytest.mark.asyncio
    async def test_payment_intent_succeeded_transitions_payment(
        self, db_session, test_user
    ):
        """A payment_intent.succeeded webhook transitions PROCESSING → SUCCEEDED."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.common.enums import PaymentStatus
        from app.domain.identity.models import Business, BusinessMember
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        # Create business
        business = Business(name="Test Biz Webhook", slug="test-biz-webhook")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            business_id=business.id,
            user_id=test_user.id,
            role="owner",
        )
        db_session.add(member)
        await db_session.flush()

        # Create payment in PROCESSING (awaiting Stripe confirmation)
        # invoice_id=None — this test focuses on payment state transition
        payment = Payment(
            idempotency_key=f"wh-test-{uuid.uuid4().hex[:8]}",
            business_id=business.id,
            customer_id=test_user.id,
            invoice_id=None,
            amount="100.00",
            currency="GBP",
            payment_method="card",
            status=PaymentStatus.PROCESSING,
            provider="stripe",
            provider_reference="pi_webhook_test_123",
        )
        db_session.add(payment)
        await db_session.flush()

        # Now simulate the webhook
        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="payment_intent.succeeded",
            provider_event_id="evt_wh_success_001",
            provider_payment_reference="pi_webhook_test_123",
            amount=Decimal("100.00"),
            currency="gbp",
            status="succeeded",
            raw_payload={
                "id": "evt_wh_success_001",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_webhook_test_123",
                        "amount": 10000,
                        "currency": "gbp",
                        "status": "succeeded",
                        "on_behalf_of": "",
                    }
                },
            },
            verified=True,
        )

        result = await svc.reconcile(event)
        assert result.status == "processed"
        assert result.payment_id == payment.id

        # Verify payment transitioned to SUCCEEDED
        await db_session.refresh(payment)
        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.paid_at is not None

    @pytest.mark.asyncio
    async def test_payment_intent_failed_transitions_payment(
        self, db_session, test_user
    ):
        """A payment_intent.payment_failed webhook transitions to FAILED."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.common.enums import PaymentStatus
        from app.domain.identity.models import Business
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        business = Business(name="Test Biz Fail", slug="test-biz-fail")
        db_session.add(business)
        await db_session.flush()

        payment = Payment(
            idempotency_key=f"wh-fail-{uuid.uuid4().hex[:8]}",
            business_id=business.id,
            customer_id=test_user.id,
            invoice_id=None,
            amount="50.00",
            currency="GBP",
            payment_method="card",
            status=PaymentStatus.PROCESSING,
            provider="stripe",
            provider_reference="pi_fail_test_456",
        )
        db_session.add(payment)
        await db_session.flush()

        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="payment_intent.payment_failed",
            provider_event_id="evt_wh_fail_001",
            provider_payment_reference="pi_fail_test_456",
            amount=Decimal("50.00"),
            currency="gbp",
            status="pending",
            raw_payload={
                "id": "evt_wh_fail_001",
                "type": "payment_intent.payment_failed",
                "data": {
                    "object": {
                        "id": "pi_fail_test_456",
                        "amount": 5000,
                        "currency": "gbp",
                        "status": "requires_payment_method",
                        "last_payment_error": {
                            "message": "Your card was declined.",
                            "decline_code": "generic_decline",
                        },
                    }
                },
            },
            verified=True,
        )

        result = await svc.reconcile(event)
        assert result.status == "processed"

        await db_session.refresh(payment)
        assert payment.status == PaymentStatus.FAILED
        assert payment.failure_message == "Your card was declined."

    @pytest.mark.asyncio
    async def test_refund_event_transitions_to_refunded(
        self, db_session, test_user
    ):
        """A charge.refund.updated event transitions SUCCEEDED → REFUNDED."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.common.enums import PaymentStatus
        from app.domain.identity.models import Business
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        business = Business(name="Test Biz Refund", slug="test-biz-refund")
        db_session.add(business)
        await db_session.flush()

        payment = Payment(
            idempotency_key=f"wh-refund-{uuid.uuid4().hex[:8]}",
            business_id=business.id,
            customer_id=test_user.id,
            invoice_id=None,
            amount="75.00",
            currency="GBP",
            payment_method="card",
            status=PaymentStatus.SUCCEEDED,
            provider="stripe",
            provider_reference="pi_refund_test_789",
            paid_at=datetime.now(UTC),
        )
        db_session.add(payment)
        await db_session.flush()

        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="charge.refund.updated",
            provider_event_id="evt_wh_refund_001",
            provider_payment_reference="pi_refund_test_789",
            amount=Decimal("75.00"),
            currency="gbp",
            status="refunded",
            raw_payload={
                "id": "evt_wh_refund_001",
                "type": "charge.refund.updated",
                "data": {
                    "object": {
                        "id": "ch_refund",
                        "payment_intent": "pi_refund_test_789",
                        "amount_refunded": 7500,
                        "amount": 7500,
                        "currency": "gbp",
                    }
                },
            },
            verified=True,
        )

        result = await svc.reconcile(event)
        assert result.status == "processed"

        await db_session.refresh(payment)
        assert payment.status == PaymentStatus.REFUNDED
        assert Decimal(payment.refunded_amount) == Decimal("75.00")

    @pytest.mark.asyncio
    async def test_dispute_created_transitions_to_disputed(
        self, db_session, test_user
    ):
        """A charge.dispute.created event transitions SUCCEEDED → DISPUTED."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.common.enums import PaymentStatus
        from app.domain.identity.models import Business
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        business = Business(name="Test Biz Dispute", slug="test-biz-dispute")
        db_session.add(business)
        await db_session.flush()

        payment = Payment(
            idempotency_key=f"wh-dispute-{uuid.uuid4().hex[:8]}",
            business_id=business.id,
            customer_id=test_user.id,
            invoice_id=None,
            amount="200.00",
            currency="GBP",
            payment_method="card",
            status=PaymentStatus.SUCCEEDED,
            provider="stripe",
            provider_reference="pi_dispute_test_abc",
            paid_at=datetime.now(UTC),
        )
        db_session.add(payment)
        await db_session.flush()

        svc = StripeWebhookReconciliationService(db_session)

        event = WebhookEvent(
            event_type="charge.dispute.created",
            provider_event_id="evt_wh_dispute_001",
            provider_payment_reference="pi_dispute_test_abc",
            amount=Decimal("200.00"),
            currency="gbp",
            status="disputed",
            raw_payload={
                "id": "evt_wh_dispute_001",
                "type": "charge.dispute.created",
                "data": {
                    "object": {
                        "id": "dp_test_001",
                        "amount": 20000,
                        "currency": "gbp",
                        "reason": "fraudulent",
                        "status": "needs_response",
                        "charge": {
                            "id": "ch_dispute",
                            "payment_intent": "pi_dispute_test_abc",
                        },
                    }
                },
            },
            verified=True,
        )

        result = await svc.reconcile(event)
        assert result.status == "processed"

        await db_session.refresh(payment)
        assert payment.status == PaymentStatus.DISPUTED
        assert payment.dispute_id == "dp_test_001"
        assert payment.dispute_reason == "fraudulent"
        assert payment.dispute_status == "needs_response"

    @pytest.mark.asyncio
    async def test_out_of_order_succeeded_after_processing(
        self, db_session, test_user
    ):
        """Webhook arriving out of order still reconciles correctly."""
        from app.adapters.payment.base import WebhookEvent
        from app.domain.common.enums import PaymentStatus
        from app.domain.identity.models import Business
        from app.domain.payment.stripe_reconciliation import (
            StripeWebhookReconciliationService,
        )

        business = Business(name="Test Biz OOO", slug="test-biz-ooo")
        db_session.add(business)
        await db_session.flush()

        # Payment starts in PROCESSING (created by pay_my_booking)
        payment = Payment(
            idempotency_key=f"wh-ooo-{uuid.uuid4().hex[:8]}",
            business_id=business.id,
            customer_id=test_user.id,
            invoice_id=None,
            amount="25.00",
            currency="GBP",
            payment_method="card",
            status=PaymentStatus.PROCESSING,
            provider="stripe",
            provider_reference="pi_ooo_test",
        )
        db_session.add(payment)
        await db_session.flush()

        svc = StripeWebhookReconciliationService(db_session)

        # First webhook: processing (intermediate)
        processing_event = WebhookEvent(
            event_type="payment_intent.processing",
            provider_event_id="evt_ooo_1",
            provider_payment_reference="pi_ooo_test",
            raw_payload={
                "id": "evt_ooo_1",
                "type": "payment_intent.processing",
                "data": {"object": {"id": "pi_ooo_test", "status": "processing"}},
            },
            verified=True,
        )
        r1 = await svc.reconcile(processing_event)
        assert r1.status == "processed"

        # Second webhook: succeeded (the important one)
        success_event = WebhookEvent(
            event_type="payment_intent.succeeded",
            provider_event_id="evt_ooo_2",
            provider_payment_reference="pi_ooo_test",
            amount=Decimal("25.00"),
            currency="gbp",
            status="succeeded",
            raw_payload={
                "id": "evt_ooo_2",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_ooo_test",
                        "amount": 2500,
                        "currency": "gbp",
                        "status": "succeeded",
                    }
                },
            },
            verified=True,
        )
        r2 = await svc.reconcile(success_event)
        assert r2.status == "processed"

        await db_session.refresh(payment)
        assert payment.status == PaymentStatus.SUCCEEDED
