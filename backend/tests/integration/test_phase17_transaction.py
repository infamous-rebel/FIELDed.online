"""Phase 17 — Transaction integration tests.

Tests the full customer transaction lifecycle over HTTP:
- Full happy path: enquiry → quote → accept → booking → execution → complete → review
- Cancelled enquiry → no review allowed
- Cross-tenant review attempt → rejected
- Public review retrieval
- Slug-to-ID resolution for enquiry creation
- Customer payment against invoice
- Failed payment → no confirmation
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.common.enums import BookingStatus
from app.domain.enquiry.models import Enquiry
from app.domain.identity.models import Business, BusinessProfile, User
from app.domain.invoice.models import Invoice
from app.domain.payment.models import Payment
from app.domain.quote.models import Quote
from app.domain.service_execution.models import ServiceExecution
from app.domain.services.models import ServiceCategory, ServiceOffer
from tests.factories import business_member_factory


@pytest_asyncio.fixture
async def biz_context(db_session: AsyncSession, second_user: User) -> dict:
    """Active business owned by second_user, with an active priced offer."""
    biz = Business(
        name=f"Txn Biz {uuid.uuid4().hex[:6]}",
        slug=f"txn-biz-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db_session.add(biz)
    await db_session.flush()

    db_session.add(
        business_member_factory(user_id=second_user.id, business_id=biz.id, role="owner")
    )
    db_session.add(BusinessProfile(business_id=biz.id, public_status="active"))
    await db_session.flush()

    category = ServiceCategory(name="Txn Cat", slug=f"txn-cat-{uuid.uuid4().hex[:8]}")
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name="Txn Service",
        slug=f"txn-service-{uuid.uuid4().hex[:8]}",
        pricing_model="fixed",
        delivery_mode="on_site",
        status="active",
        pricing_config={"amount": "150.00", "currency": "GBP"},
    )
    db_session.add(offer)
    await db_session.flush()

    return {"biz": biz, "offer": offer}


@pytest_asyncio.fixture
async def biz_auth_headers(client: AsyncClient, second_user: User) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": second_user.email, "password": "testpassword123"},
    )
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _submit_review(client: AsyncClient, auth: dict, execution_id, rating: int = 5):
    return await client.post(
        "/api/v1/my-reviews",
        headers=auth,
        json={
            "service_execution_id": str(execution_id),
            "rating": rating,
            "title": "Great service",
            "body": "Everything went smoothly.",
        },
    )


async def _drive_to_completed_execution(
    client: AsyncClient,
    *,
    biz_context: dict,
    customer_auth: dict,
    biz_auth: dict,
) -> dict:
    """Drive enquiry → quote → accept → booking → execution → complete."""
    biz, offer = biz_context["biz"], biz_context["offer"]

    # Enquiry (customer) — business_id resolved from the public slug page
    resp = await client.get(f"/api/v1/public/business/{biz.slug}/services/{offer.slug}")
    assert resp.status_code == 200
    business_id = resp.json()["business_id"]

    resp = await client.post(
        f"/api/v1/enquiries/{business_id}/enquiries",
        headers=customer_auth,
        json={
            "service_offer_id": str(offer.id),
            "subject": "Need this service",
            "message": "Please quote me.",
        },
    )
    assert resp.status_code == 201, resp.text
    enquiry_id = resp.json()["id"]

    # Business receives the enquiry (SUBMITTED → RECEIVED)
    resp = await client.post(
        f"/api/v1/businesses/{business_id}/enquiries/{enquiry_id}/transition",
        headers=biz_auth,
        json={"target_status": "received"},
    )
    assert resp.status_code == 200, resp.text

    # Quote (business)
    resp = await client.post(
        f"/api/v1/businesses/{business_id}/quotes",
        headers=biz_auth,
        json={"enquiry_id": enquiry_id},
    )
    assert resp.status_code == 201, resp.text
    quote_id = resp.json()["id"]

    # Issue quote (business)
    resp = await client.post(
        f"/api/v1/businesses/{business_id}/quotes/{quote_id}/transition",
        headers=biz_auth,
        json={"target_status": "issued"},
    )
    assert resp.status_code == 200, resp.text

    # Accept quote (customer)
    resp = await client.post(
        f"/api/v1/businesses/my-quotes/{quote_id}/transition",
        headers=customer_auth,
        json={"target_status": "accepted"},
    )
    assert resp.status_code == 200, resp.text

    # Booking (customer)
    resp = await client.post(
        "/api/v1/businesses/my-bookings",
        headers=customer_auth,
        json={
            "quote_id": quote_id,
            "requested_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    booking_id = resp.json()["id"]

    # Confirm booking, then move it to in_progress before completion.
    # Deterministic chain: requested → proposed → accepted → confirmed.
    for status in ("proposed", "accepted", "confirmed", "in_progress"):
        resp = await client.post(
            f"/api/v1/businesses/{business_id}/bookings/{booking_id}/transition",
            headers=biz_auth,
            json={"target_status": status},
        )
        assert resp.status_code == 200, resp.text

    # Execution (business)
    resp = await client.post(
        f"/api/v1/businesses/{business_id}/service-executions",
        headers=biz_auth,
        json={"booking_id": booking_id},
    )
    assert resp.status_code == 201, resp.text
    execution_id = resp.json()["id"]

    # Start + complete (business)
    resp = await client.post(
        f"/api/v1/businesses/{business_id}/service-executions/{execution_id}/transition",
        headers=biz_auth,
        json={"target_status": "in_progress"},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/api/v1/businesses/{business_id}/service-executions/{execution_id}/complete",
        headers=biz_auth,
    )
    assert resp.status_code == 200, resp.text

    return {
        "business_id": business_id,
        "enquiry_id": enquiry_id,
        "quote_id": quote_id,
        "booking_id": booking_id,
        "execution_id": execution_id,
    }


class TestFullHappyPath:
    """The complete customer transaction lifecycle over HTTP."""

    @pytest.mark.asyncio
    async def test_full_happy_path_enquiry_to_review(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        biz_context: dict,
        auth_headers: dict,
        biz_auth_headers: dict,
    ):
        chain = await _drive_to_completed_execution(
            client,
            biz_context=biz_context,
            customer_auth=auth_headers,
            biz_auth=biz_auth_headers,
        )

        response = await _submit_review(client, auth_headers, chain["execution_id"])
        assert response.status_code == 201, response.text
        review = response.json()
        assert review["rating"] == 5
        assert review["service_execution_id"] == chain["execution_id"]
        assert review["status"] == "visible"

    @pytest.mark.asyncio
    async def test_slug_to_id_resolution_for_enquiry_creation(
        self,
        client: AsyncClient,
        biz_context: dict,
        auth_headers: dict,
    ):
        biz, offer = biz_context["biz"], biz_context["offer"]

        response = await client.get(f"/api/v1/public/business/{biz.slug}/services/{offer.slug}")
        assert response.status_code == 200
        data = response.json()
        business_id = data["business_id"]
        uuid.UUID(business_id)  # must be a valid business UUID

        # The resolved ID enables authenticated enquiry creation
        response = await client.post(
            f"/api/v1/enquiries/{business_id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Slug resolved",
                "message": "Enquiry created from public slug resolution.",
            },
        )
        assert response.status_code == 201, response.text


class TestReviewTrustBoundaries:
    """Reviews are rejected outside the trust chain."""

    @pytest.mark.asyncio
    async def test_cancelled_enquiry_no_review_allowed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        biz_context: dict,
        test_user: User,
        second_user: User,
        auth_headers: dict,
    ):
        biz, offer = biz_context["biz"], biz_context["offer"]

        enquiry = Enquiry(
            reference=f"ENQ-{uuid.uuid4().hex[:8]}",
            customer_id=test_user.id,
            business_id=biz.id,
            service_offer_id=offer.id,
            subject="Cancelled",
            message="Cancelled enquiry",
            status="cancelled",
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
            requested_at=datetime.now(UTC) + timedelta(days=1),
            currency="GBP",
            status=BookingStatus.CONFIRMED,
        )
        db_session.add(booking)
        await db_session.flush()

        execution = ServiceExecution(
            business_id=biz.id,
            customer_id=test_user.id,
            booking_id=booking.id,
            service_offer_id=offer.id,
            quote_id=quote.id,
            status="completed",
            completed_at=datetime.now(UTC),
            completed_by=second_user.id,
        )
        db_session.add(execution)
        await db_session.flush()

        response = await _submit_review(client, auth_headers, execution.id)
        assert response.status_code == 422
        assert "declined or cancelled" in response.text

    @pytest.mark.asyncio
    async def test_cross_tenant_review_attempt_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        biz_context: dict,
        test_user: User,
        second_user: User,
        second_auth_headers: dict,
    ):
        """Another customer cannot review a service they did not receive."""
        biz, offer = biz_context["biz"], biz_context["offer"]

        enquiry = Enquiry(
            reference=f"ENQ-{uuid.uuid4().hex[:8]}",
            customer_id=test_user.id,
            business_id=biz.id,
            service_offer_id=offer.id,
            subject="Not yours",
            message="Someone else's service",
            status="quoted",
        )
        db_session.add(enquiry)
        await db_session.flush()

        quote = Quote(
            reference=f"QUO-{uuid.uuid4().hex[:8]}",
            customer_id=enquiry.customer_id,
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
            customer_id=enquiry.customer_id,
            business_id=biz.id,
            quote_id=quote.id,
            enquiry_id=enquiry.id,
            service_offer_id=offer.id,
            requested_at=datetime.now(UTC) + timedelta(days=1),
            currency="GBP",
            status=BookingStatus.CONFIRMED,
        )
        db_session.add(booking)
        await db_session.flush()

        execution = ServiceExecution(
            business_id=biz.id,
            customer_id=enquiry.customer_id,
            booking_id=booking.id,
            service_offer_id=offer.id,
            quote_id=quote.id,
            status="completed",
            completed_at=datetime.now(UTC),
            completed_by=second_user.id,
        )
        db_session.add(execution)
        await db_session.flush()

        # second_user owns the business but did NOT receive the service
        response = await _submit_review(client, second_auth_headers, execution.id)
        assert response.status_code == 422
        assert "does not own" in response.text

    @pytest.mark.asyncio
    async def test_public_review_retrieval(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        biz_context: dict,
        auth_headers: dict,
        biz_auth_headers: dict,
    ):
        biz = biz_context["biz"]

        chain = await _drive_to_completed_execution(
            client,
            biz_context=biz_context,
            customer_auth=auth_headers,
            biz_auth=biz_auth_headers,
        )
        response = await _submit_review(client, auth_headers, chain["execution_id"], rating=4)
        assert response.status_code == 201

        response = await client.get(f"/api/v1/public/business/{biz.slug}/reviews")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["average_rating"] == pytest.approx(4.0)
        item = data["items"][0]
        # Public schema must not leak internal identifiers
        assert item["rating"] == 4
        assert "customer_id" not in item
        assert "business_id" not in item


class TestCustomerPayment:
    """Post-service payment against the completion invoice."""

    @pytest.mark.asyncio
    async def test_customer_payment_against_invoice(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        biz_context: dict,
        test_user: User,
        second_user: User,
        auth_headers: dict,
    ):
        biz, offer = biz_context["biz"], biz_context["offer"]

        enquiry = Enquiry(
            reference=f"ENQ-{uuid.uuid4().hex[:8]}",
            customer_id=test_user.id,
            business_id=biz.id,
            service_offer_id=offer.id,
            subject="Pay me",
            message="Payment test",
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
            requested_at=datetime.now(UTC) + timedelta(days=1),
            currency="GBP",
            status=BookingStatus.CONFIRMED,
        )
        db_session.add(booking)
        await db_session.flush()

        execution = ServiceExecution(
            business_id=biz.id,
            customer_id=test_user.id,
            booking_id=booking.id,
            service_offer_id=offer.id,
            quote_id=quote.id,
            status="completed",
            completed_at=datetime.now(UTC),
            completed_by=second_user.id,
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
            subtotal="150.00",
            discount="0.00",
            tax="0.00",
            total="150.00",
            payment_status="unpaid",
            status="issued",
        )
        db_session.add(invoice)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/businesses/my-bookings/{booking.id}/pay",
            headers=auth_headers,
            json={
                "payment_method": "card",
                "idempotency_key": f"pay-{uuid.uuid4().hex[:12]}",
            },
        )
        assert response.status_code == 201, response.text
        payment = response.json()
        assert payment["status"] == "succeeded"
        assert payment["amount"] == "150.00"
        assert payment["invoice_id"] == str(invoice.id)

    @pytest.mark.asyncio
    async def test_failed_payment_no_confirmation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        biz_context: dict,
        test_user: User,
        auth_headers: dict,
    ):
        """Payment before service completion fails and records nothing."""
        biz, offer = biz_context["biz"], biz_context["offer"]

        enquiry = Enquiry(
            reference=f"ENQ-{uuid.uuid4().hex[:8]}",
            customer_id=test_user.id,
            business_id=biz.id,
            service_offer_id=offer.id,
            subject="Too early",
            message="Service not completed",
            status="quoted",
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
            requested_at=datetime.now(UTC) + timedelta(days=1),
            currency="GBP",
            status=BookingStatus.CONFIRMED,
        )
        db_session.add(booking)
        await db_session.flush()

        execution = ServiceExecution(
            business_id=biz.id,
            customer_id=test_user.id,
            booking_id=booking.id,
            service_offer_id=offer.id,
            quote_id=quote.id,
            status="scheduled",
        )
        db_session.add(execution)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/businesses/my-bookings/{booking.id}/pay",
            headers=auth_headers,
            json={
                "payment_method": "card",
                "idempotency_key": f"pay-{uuid.uuid4().hex[:12]}",
            },
        )
        assert response.status_code == 422
        assert "completed first" in response.text

        # No payment confirmation exists for the customer
        result = await db_session.execute(
            select(Payment).where(Payment.customer_id == test_user.id)
        )
        assert result.scalars().all() == []
