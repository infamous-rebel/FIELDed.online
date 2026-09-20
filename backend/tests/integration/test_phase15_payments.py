"""Phase 15 — Payment API integration tests.

Tests the HTTP endpoints for payment creation, status tracking,
refunds, webhook handling, and invoice payment status.
Verifies authorization, tenant isolation, and idempotency.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.common.enums import BookingStatus, InvoicePaymentStatus
from app.domain.enquiry.models import Enquiry
from app.domain.identity.models import Business, BusinessMember, CustomerProfile, User
from app.domain.invoice.models import Invoice, InvoiceLineItem
from app.domain.payment.models import Payment
from app.domain.quote.models import Quote
from app.domain.services.models import ServiceCategory, ServiceOffer
from app.security.password import hash_password
from tests.factories import (
    business_factory,
    business_member_factory,
    service_category_factory,
)


@pytest_asyncio.fixture
async def biz_with_member(db_session: AsyncSession) -> tuple[User, Business]:
    """Create a business with an owner."""
    user = User(
        email=f"paybiz-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()

    profile = CustomerProfile(user_id=user.id, first_name="Pay", last_name="Biz")
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
async def invoice_for_payment(
    db_session: AsyncSession,
    test_user: User,
    biz_with_member: tuple[User, Business],
) -> Invoice:
    """Create a paid/unpaid invoice for payment tests."""
    owner_user, biz = biz_with_member

    category = service_category_factory()
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name=f"Pay Svc {uuid.uuid4().hex[:6]}",
        slug=f"pay-svc-{uuid.uuid4().hex[:6]}",
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
        subject="Payment test enquiry",
        message="Testing payment flow",
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
        amount="150.00",
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
        requested_at=datetime.now(timezone.utc) + timedelta(days=2),
        currency="GBP",
        status=BookingStatus.COMPLETED,
    )
    db_session.add(booking)
    await db_session.flush()

    # Create invoice directly (bypassing service execution for speed)
    from app.domain.service_execution.models import ServiceExecution

    execution = ServiceExecution(
        business_id=biz.id,
        customer_id=test_user.id,
        booking_id=booking.id,
        service_offer_id=offer.id,
        quote_id=quote.id,
        status="completed",
        completed_at=datetime.now(timezone.utc),
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
        issue_date=datetime.now(timezone.utc),
        currency="GBP",
        subtotal="150.00",
        discount="0.00",
        tax="0.00",
        total="150.00",
        payment_status="unpaid",
        status="issued",
    )
    db_session.add(invoice)
    await db_session.flush()

    line_item = InvoiceLineItem(
        invoice_id=invoice.id,
        description="Test service",
        quantity="1.00",
        unit_price="150.00",
        discount="0.00",
        tax="0.00",
        line_total="150.00",
        currency="GBP",
        sort_order=0,
    )
    db_session.add(line_item)
    await db_session.flush()

    return invoice


@pytest_asyncio.fixture
async def biz_auth_headers(client: AsyncClient, biz_with_member: tuple[User, Business]) -> dict:
    """Get auth headers for the business owner."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": biz_with_member[0].email, "password": "testpassword123"},
    )
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class TestPaymentCreation:
    """Test payment creation via API."""

    async def test_create_payment(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Create a payment for an invoice."""
        _, biz = biz_with_member

        response = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"pay-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "succeeded"  # Stub auto-succeeds
        assert data["amount"] == "150.00"
        assert data["currency"] == "GBP"
        assert data["provider_reference"] is not None

    async def test_create_payment_idempotent(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Duplicate idempotency key returns existing payment."""
        _, biz = biz_with_member
        idem_key = f"idem-{uuid.uuid4().hex[:16]}"

        # First request
        response1 = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": idem_key,
            },
            headers=biz_auth_headers,
        )
        assert response1.status_code == 201
        payment_id = response1.json()["id"]

        # Second request with same idempotency key
        response2 = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": idem_key,
            },
            headers=biz_auth_headers,
        )
        assert response2.status_code == 201
        assert response2.json()["id"] == payment_id

    async def test_create_payment_exceeds_balance(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Payment amount exceeding outstanding balance is rejected."""
        _, biz = biz_with_member

        response = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "999.99",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"over-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )
        assert response.status_code == 422

    async def test_create_payment_currency_mismatch(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Payment currency not matching invoice is rejected."""
        _, biz = biz_with_member

        response = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "USD",
                "payment_method": "card",
                "idempotency_key": f"cur-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )
        assert response.status_code == 422


class TestPaymentRetrieval:
    """Test payment retrieval endpoints."""

    async def test_list_business_payments(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """List payments for a business."""
        _, biz = biz_with_member

        # Create a payment first
        await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"list-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/payments",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_get_business_payment(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Get a specific payment."""
        _, biz = biz_with_member

        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"get-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )
        payment_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/payments/{payment_id}",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["id"] == payment_id


class TestInvoicePaymentStatus:
    """Test invoice payment status endpoint."""

    async def test_invoice_payment_status_after_payment(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Invoice payment status updates after successful payment."""
        _, biz = biz_with_member

        # Pay the invoice in full
        await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"full-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )

        # Check invoice payment status
        response = await client.get(
            f"/api/v1/businesses/{biz.id}/invoices/{invoice_for_payment.id}/payment-status",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["paid_amount"] == "150.00"
        assert data["outstanding_amount"] == "0.00"

    async def test_invoice_partial_payment(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Partial payment shows correct outstanding balance."""
        _, biz = biz_with_member

        # Pay partially
        await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "50.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"partial-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/invoices/{invoice_for_payment.id}/payment-status",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["paid_amount"] == "50.00"
        assert data["outstanding_amount"] == "100.00"


class TestPaymentRefund:
    """Test payment refund endpoint."""

    async def test_full_refund(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        invoice_for_payment: Invoice,
        biz_auth_headers: dict,
    ):
        """Full refund of a succeeded payment."""
        _, biz = biz_with_member

        # Create and succeed a payment
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/payments",
            json={
                "invoice_id": str(invoice_for_payment.id),
                "amount": "150.00",
                "currency": "GBP",
                "payment_method": "card",
                "idempotency_key": f"refund-{uuid.uuid4().hex[:16]}",
            },
            headers=biz_auth_headers,
        )
        payment_id = create_resp.json()["id"]

        # Refund it
        response = await client.post(
            f"/api/v1/businesses/{biz.id}/payments/{payment_id}/refund",
            json={"reason": "Customer request"},
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "refunded"
        assert data["refunded_amount"] == "150.00"


class TestPaymentWebhook:
    """Test payment webhook endpoint."""

    async def test_webhook_accepted(
        self,
        client: AsyncClient,
    ):
        """Webhook endpoint accepts provider events."""
        response = await client.post(
            "/api/v1/webhooks/payment/stub",
            json={
                "type": "payment_intent.succeeded",
                "id": "evt_test",
                "payment_intent": "pi_nonexistent",
                "status": "succeeded",
            },
        )
        # Should return 200 even for unknown reference
        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True


class TestPaymentAuthorization:
    """Test payment authorization and tenant isolation."""

    async def test_customer_cannot_access_business_payments(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        auth_headers: dict,  # Customer auth
    ):
        """Customer cannot list business payments."""
        _, biz = biz_with_member

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/payments",
            headers=auth_headers,
        )
        assert response.status_code in (401, 403)

    async def test_cross_tenant_payment_access_denied(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        second_auth_headers: dict,  # Different business owner
    ):
        """Another business cannot access payments."""
        _, biz = biz_with_member

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/payments",
            headers=second_auth_headers,
        )
        assert response.status_code in (401, 403)

    async def test_customer_can_list_own_payments(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Customer can list their own payments."""
        response = await client.get(
            "/api/v1/my-payments",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
