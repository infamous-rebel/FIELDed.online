"""Phase 15 — Stripe sandbox E2E integration tests.

Tests the full payment flow through the HTTP API using the
StripePaymentProvider with a mock HTTP transport.  This proves
the real Stripe integration path without requiring external
credentials or network access.

Covers:
- Create payment → Stripe PaymentIntent creation
- Successful payment via webhook
- Webhook signature rejection at the HTTP endpoint
- Valid webhook processing through the endpoint
- Duplicate webhook idempotency
- Refund flow through the API
- Tenant isolation with Stripe provider
- Invoice/payment status consistency after Stripe payment
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.payment.stripe_provider import StripePaymentProvider
from app.domain.booking.models import Booking
from app.domain.common.enums import BookingStatus
from app.domain.enquiry.models import Enquiry
from app.domain.identity.models import Business, CustomerProfile, User
from app.domain.invoice.models import Invoice, InvoiceLineItem
from app.domain.quote.models import Quote
from app.domain.services.models import ServiceOffer
from app.security.password import hash_password
from tests.factories import (
    business_factory,
    business_member_factory,
    service_category_factory,
)

# ---------------------------------------------------------------------------
# Mock Stripe HTTP transport
# ---------------------------------------------------------------------------


class SandboxStripeHTTPClient:
    """Mock Stripe HTTP transport for sandbox E2E tests."""

    name = "sandbox-mock"

    def __init__(self) -> None:
        self._payment_intents: dict[str, dict] = {}
        self._refunds: dict[str, dict] = {}
        self._pi_counter = 0
        self._re_counter = 0
        self.auto_succeed: bool = True

    @staticmethod
    def _parse_post_data(post_data: Any) -> dict:
        if not post_data:
            return {}
        if isinstance(post_data, (bytes, bytearray)):
            post_data = post_data.decode("utf-8")
        if isinstance(post_data, str):
            try:
                return json.loads(post_data)
            except (json.JSONDecodeError, ValueError):
                parsed = parse_qs(post_data, keep_blank_values=True)
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        if isinstance(post_data, dict):
            return post_data
        return {}

    def request(self, method, url, headers, post_data=None, **kwargs):
        method_lower = method.lower()
        params = self._parse_post_data(post_data)

        if "payment_intents" in url and method_lower == "post":
            self._pi_counter += 1
            pi_id = f"pi_sandbox_{self._pi_counter:05d}"
            status = "succeeded" if self.auto_succeed else "requires_payment_method"
            pi = {
                "id": pi_id,
                "object": "payment_intent",
                "amount": params.get("amount", 0),
                "currency": params.get("currency", "gbp"),
                "status": status,
                "client_secret": f"{pi_id}_secret_{uuid.uuid4().hex[:12]}",
                "metadata": params.get("metadata", {}),
            }
            self._payment_intents[pi_id] = pi
            return json.dumps(pi), 200, {}

        if "payment_intents" in url and method_lower == "get":
            pi_id = url.rstrip("/").split("/")[-1]
            pi = self._payment_intents.get(pi_id)
            if pi:
                return json.dumps(pi), 200, {}
            return (
                json.dumps({"error": {"type": "invalid_request_error", "message": "Not found"}}),
                404,
                {},
            )

        if "refunds" in url and method_lower == "post":
            self._re_counter += 1
            re_id = f"re_sandbox_{self._re_counter:05d}"
            refund = {
                "id": re_id,
                "object": "refund",
                "amount": params.get("amount", 0),
                "currency": "gbp",
                "status": "succeeded",
                "payment_intent": params.get("payment_intent", ""),
            }
            self._refunds[re_id] = refund
            return json.dumps(refund), 200, {}

        return json.dumps({"error": {"message": "Not found"}}), 404, {}

    def request_with_retries(self, method, url, headers, post_data=None, **kwargs):
        return self.request(method, url, headers, post_data, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sandbox_http_client():
    return SandboxStripeHTTPClient()


@pytest_asyncio.fixture
async def stripe_provider_with_mock(sandbox_http_client):
    return StripePaymentProvider(
        api_key="sk_test_sandbox_key",
        webhook_secret="whsec_sandbox_secret",
        http_client=sandbox_http_client,
    )


@pytest_asyncio.fixture
async def webhook_secret_enabled(app):
    """Enable webhook secret verification on the test app."""
    app.state.settings.payment_webhook_secret = "whsec_sandbox_secret"
    yield
    app.state.settings.payment_webhook_secret = ""


@pytest_asyncio.fixture
async def biz_with_member(db_session: AsyncSession) -> tuple[User, Business]:
    user = User(
        email=f"stripe-biz-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    profile = CustomerProfile(user_id=user.id, first_name="Stripe", last_name="Biz")
    db_session.add(profile)
    await db_session.flush()
    biz = business_factory()
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    await db_session.refresh(user, attribute_names=["customer_profile", "business_memberships"])
    return user, biz


@pytest_asyncio.fixture
async def invoice_for_stripe(
    db_session: AsyncSession,
    test_user: User,
    biz_with_member: tuple[User, Business],
) -> Invoice:
    owner_user, biz = biz_with_member
    category = service_category_factory()
    db_session.add(category)
    await db_session.flush()
    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name=f"Stripe Svc {uuid.uuid4().hex[:6]}",
        slug=f"stripe-svc-{uuid.uuid4().hex[:6]}",
        pricing_model="fixed",
        delivery_mode="on_site",
        status="active",
    )
    db_session.add(offer)
    await db_session.flush()
    enquiry = Enquiry(
        reference=f"ENQ-{uuid.uuid4().hex[:8]}",
        customer_id=test_user.id,
        business_id=biz.id,
        service_offer_id=offer.id,
        subject="Stripe test",
        message="Testing",
        status="completed",
    )
    db_session.add(enquiry)
    await db_session.flush()
    quote = Quote(
        reference=f"QUO-{uuid.uuid4().hex[:8]}",
        customer_id=test_user.id,
        business_id=biz.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        amount="200.00",
        currency="GBP",
        status="accepted",
    )
    db_session.add(quote)
    await db_session.flush()
    booking = Booking(
        reference=f"BKG-{uuid.uuid4().hex[:8]}",
        customer_id=test_user.id,
        business_id=biz.id,
        quote_id=quote.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        requested_at=datetime.now(UTC) + timedelta(days=2),
        currency="GBP",
        status=BookingStatus.COMPLETED,
    )
    db_session.add(booking)
    await db_session.flush()
    from app.domain.service_execution.models import ServiceExecution

    execution = ServiceExecution(
        business_id=biz.id,
        customer_id=test_user.id,
        booking_id=booking.id,
        service_offer_id=offer.id,
        quote_id=quote.id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=owner_user.id,
    )
    db_session.add(execution)
    await db_session.flush()
    invoice = Invoice(
        business_id=biz.id,
        customer_id=test_user.id,
        service_execution_id=execution.id,
        booking_id=booking.id,
        quote_id=quote.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
        issue_date=datetime.now(UTC),
        currency="GBP",
        subtotal="200.00",
        discount="0.00",
        tax="0.00",
        total="200.00",
        payment_status="unpaid",
        status="issued",
    )
    db_session.add(invoice)
    await db_session.flush()
    line_item = InvoiceLineItem(
        invoice_id=invoice.id,
        description="Stripe test service",
        quantity="1.00",
        unit_price="200.00",
        discount="0.00",
        tax="0.00",
        line_total="200.00",
        currency="GBP",
        sort_order=0,
    )
    db_session.add(line_item)
    await db_session.flush()
    return invoice


@pytest_asyncio.fixture
async def biz_auth_headers(client: AsyncClient, biz_with_member: tuple[User, Business]) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": biz_with_member[0].email, "password": "testpassword123"},
    )
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _make_stripe_webhook(event_type, pi_id, status, amount=20000, secret="whsec_sandbox_secret", event_id=None):
    """Create a signed Stripe webhook payload."""
    payload_dict = {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": pi_id,
                "object": "payment_intent",
                "amount": amount,
                "currency": "gbp",
                "status": status,
                "metadata": {},
            }
        },
    }
    payload_bytes = json.dumps(payload_dict).encode()
    timestamp = "1234567890"
    signed_payload = f"{timestamp}.{payload_bytes.decode()}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    sig_header = f"t={timestamp},v1={sig}"
    return payload_bytes, sig_header


# ---------------------------------------------------------------------------
# Sandbox E2E tests
# ---------------------------------------------------------------------------


class TestStripeSandboxPaymentCreation:
    async def test_create_payment_creates_stripe_payment_intent(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        stripe_provider_with_mock,
    ):
        _, biz = biz_with_member
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            response = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": f"stripe-e2e-{uuid.uuid4().hex[:16]}",
                },
                headers=biz_auth_headers,
            )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "succeeded"
        assert data["provider"] == "stripe"
        assert data["provider_reference"].startswith("pi_")

    async def test_create_payment_idempotent_with_stripe(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        stripe_provider_with_mock,
    ):
        _, biz = biz_with_member
        idem_key = f"stripe-idem-{uuid.uuid4().hex[:16]}"
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            resp1 = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": idem_key,
                },
                headers=biz_auth_headers,
            )
            assert resp1.status_code == 201
            payment_id = resp1.json()["id"]
            resp2 = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": idem_key,
                },
                headers=biz_auth_headers,
            )
            assert resp2.status_code == 201
            assert resp2.json()["id"] == payment_id


class TestStripeSandboxWebhook:
    async def test_webhook_signature_rejection(
        self,
        client,
        biz_with_member,
        stripe_provider_with_mock,
        webhook_secret_enabled,
    ):
        payload = json.dumps({"type": "payment_intent.succeeded"}).encode()
        bad_sig = "t=1234567890,v1=" + "0" * 64
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            response = await client.post(
                "/api/v1/webhooks/payment/stripe",
                content=payload,
                headers={"Stripe-Signature": bad_sig, "Content-Type": "application/json"},
            )
        assert response.status_code == 401

    async def test_valid_webhook_updates_payment(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        stripe_provider_with_mock,
        sandbox_http_client,
        webhook_secret_enabled,
    ):
        _, biz = biz_with_member
        sandbox_http_client.auto_succeed = False
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            create_resp = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": f"webhook-e2e-{uuid.uuid4().hex[:16]}",
                },
                headers=biz_auth_headers,
            )
            assert create_resp.status_code == 201
            pi_ref = create_resp.json()["provider_reference"]
            payload_bytes, sig_header = _make_stripe_webhook(
                "payment_intent.succeeded",
                pi_ref,
                "succeeded",
                20000,
            )
            webhook_resp = await client.post(
                "/api/v1/webhooks/payment/stripe",
                content=payload_bytes,
                headers={"Stripe-Signature": sig_header, "Content-Type": "application/json"},
            )
        assert webhook_resp.status_code == 200
        assert webhook_resp.json()["received"] is True

    async def test_duplicate_webhook_idempotent(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        stripe_provider_with_mock,
        sandbox_http_client,
        webhook_secret_enabled,
    ):
        _, biz = biz_with_member
        sandbox_http_client.auto_succeed = False
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            create_resp = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": f"dup-wh-{uuid.uuid4().hex[:16]}",
                },
                headers=biz_auth_headers,
            )
            pi_ref = create_resp.json()["provider_reference"]
            event_id = f"evt_dup_{uuid.uuid4().hex[:16]}"
            payload_bytes, sig_header = _make_stripe_webhook(
                "payment_intent.succeeded",
                pi_ref,
                "succeeded",
                20000,
                event_id=event_id,
            )
            resp1 = await client.post(
                "/api/v1/webhooks/payment/stripe",
                content=payload_bytes,
                headers={"Stripe-Signature": sig_header, "Content-Type": "application/json"},
            )
            resp2 = await client.post(
                "/api/v1/webhooks/payment/stripe",
                content=payload_bytes,
                headers={"Stripe-Signature": sig_header, "Content-Type": "application/json"},
            )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["payment_id"] == resp2.json()["payment_id"]


class TestStripeSandboxRefund:
    async def test_full_refund_through_stripe(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        stripe_provider_with_mock,
    ):
        _, biz = biz_with_member
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            create_resp = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": f"refund-e2e-{uuid.uuid4().hex[:16]}",
                },
                headers=biz_auth_headers,
            )
            assert create_resp.status_code == 201
            payment_id = create_resp.json()["id"]
            refund_resp = await client.post(
                f"/api/v1/businesses/{biz.id}/payments/{payment_id}/refund",
                json={"reason": "Customer cancellation"},
                headers=biz_auth_headers,
            )
        assert refund_resp.status_code == 200
        data = refund_resp.json()
        assert data["status"] == "refunded"
        assert data["refunded_amount"] == "200.00"


class TestStripeSandboxInvoiceConsistency:
    async def test_invoice_status_after_stripe_payment(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        stripe_provider_with_mock,
    ):
        _, biz = biz_with_member
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": f"inv-status-{uuid.uuid4().hex[:16]}",
                },
                headers=biz_auth_headers,
            )
            status_resp = await client.get(
                f"/api/v1/businesses/{biz.id}/invoices/{invoice_for_stripe.id}/payment-status",
                headers=biz_auth_headers,
            )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["paid_amount"] == "200.00"
        assert data["outstanding_amount"] == "0.00"


class TestStripeSandboxTenantIsolation:
    async def test_cross_tenant_payment_access_denied(
        self,
        client,
        biz_with_member,
        invoice_for_stripe,
        biz_auth_headers,
        second_user,
        stripe_provider_with_mock,
    ):
        _, biz = biz_with_member
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            create_resp = await client.post(
                f"/api/v1/businesses/{biz.id}/payments",
                json={
                    "invoice_id": str(invoice_for_stripe.id),
                    "amount": "200.00",
                    "currency": "GBP",
                    "payment_method": "card",
                    "idempotency_key": f"tenant-{uuid.uuid4().hex[:16]}",
                },
                headers=biz_auth_headers,
            )
            assert create_resp.status_code == 201
        second_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": second_user.email, "password": "testpassword123"},
        )
        second_headers = {"Authorization": f"Bearer {second_resp.json()['access_token']}"}
        with patch("app.api.v1.payments._payment_provider", return_value=stripe_provider_with_mock):
            list_resp = await client.get(
                f"/api/v1/businesses/{biz.id}/payments",
                headers=second_headers,
            )
        assert list_resp.status_code in (401, 403, 404)
