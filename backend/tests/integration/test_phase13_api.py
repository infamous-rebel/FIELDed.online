"""Phase 13 — API integration tests.

Tests the HTTP endpoints for service executions, invoices, and ledger.
Verifies authorization, tenant isolation, and correct API responses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.common.enums import BookingStatus
from app.domain.enquiry.models import Enquiry
from app.domain.identity.models import Business, CustomerProfile, User
from app.domain.quote.models import Quote
from app.domain.services.models import ServiceOffer
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
        email=f"biz-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()

    profile = CustomerProfile(user_id=user.id, first_name="Biz", last_name="User")
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
async def booking_for_api(
    db_session: AsyncSession,
    test_user: User,
    biz_with_member: tuple[User, Business],
) -> Booking:
    """Create a confirmed booking for API tests."""
    owner_user, biz = biz_with_member

    category = service_category_factory()
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name=f"API Svc {uuid.uuid4().hex[:6]}",
        slug=f"api-svc-{uuid.uuid4().hex[:6]}",
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
        subject="API test enquiry",
        message="Testing the API",
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
        status=BookingStatus.CONFIRMED,
    )
    db_session.add(booking)
    await db_session.flush()

    return booking


@pytest_asyncio.fixture
async def biz_auth_headers(client: AsyncClient, biz_with_member: tuple[User, Business]) -> dict:
    """Get auth headers for the business owner."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": biz_with_member[0].email, "password": "testpassword123"},
    )
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class TestServiceExecutionAPI:
    """Test service execution API endpoints."""

    async def test_create_execution(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """Create a service execution via API."""
        _, biz = biz_with_member

        response = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "scheduled"
        assert data["booking_id"] == str(booking_for_api.id)

    async def test_list_executions(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """List service executions for a business."""
        _, biz = biz_with_member

        # Create an execution first
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/service-executions",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_complete_execution(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """Complete a service execution via API (creates invoice + ledger)."""
        _, biz = biz_with_member

        # Create execution
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        execution_id = create_resp.json()["id"]

        # Start it
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/transition",
            json={"target_status": "in_progress"},
            headers=biz_auth_headers,
        )

        # Complete it
        response = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/complete",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    async def test_unauthorized_access_rejected(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        auth_headers: dict,  # Customer auth headers, not business
    ):
        """Customer cannot access business service execution endpoints."""
        _, biz = biz_with_member

        response = await client.get(
            f"/api/v1/businesses/{biz.id}/service-executions",
            headers=auth_headers,
        )
        assert response.status_code in (401, 403)


class TestInvoiceAPI:
    """Test invoice API endpoints."""

    async def test_list_invoices_after_completion(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """Invoices appear after service completion."""
        _, biz = biz_with_member

        # Create and complete execution
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        execution_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/transition",
            json={"target_status": "in_progress"},
            headers=biz_auth_headers,
        )
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/complete",
            headers=biz_auth_headers,
        )

        # List invoices
        response = await client.get(
            f"/api/v1/businesses/{biz.id}/invoices",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["total"] == "200.00"

    async def test_download_invoice_pdf(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """Download invoice PDF."""
        _, biz = biz_with_member

        # Create and complete execution
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        execution_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/transition",
            json={"target_status": "in_progress"},
            headers=biz_auth_headers,
        )
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/complete",
            headers=biz_auth_headers,
        )

        # Get invoice
        inv_resp = await client.get(
            f"/api/v1/businesses/{biz.id}/invoices",
            headers=biz_auth_headers,
        )
        invoice_id = inv_resp.json()[0]["id"]

        # Download PDF
        response = await client.get(
            f"/api/v1/businesses/{biz.id}/invoices/{invoice_id}/pdf",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert len(response.content) > 0


class TestLedgerAPI:
    """Test ledger API endpoints."""

    async def test_ledger_summary_after_completion(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """Ledger summary reflects completed services."""
        _, biz = biz_with_member

        # Create and complete execution
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        execution_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/transition",
            json={"target_status": "in_progress"},
            headers=biz_auth_headers,
        )
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/complete",
            headers=biz_auth_headers,
        )

        # Get summary
        response = await client.get(
            f"/api/v1/businesses/{biz.id}/ledger/summary",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_entries"] == 1
        assert data["total_net"] == "200.00"

    async def test_csv_export(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """CSV export returns CSV data."""
        _, biz = biz_with_member

        # Create and complete execution
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        execution_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/transition",
            json={"target_status": "in_progress"},
            headers=biz_auth_headers,
        )
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/complete",
            headers=biz_auth_headers,
        )

        # Export CSV
        response = await client.get(
            f"/api/v1/businesses/{biz.id}/ledger/export/csv",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "FIELDed" in response.text

    async def test_pdf_export(
        self,
        client: AsyncClient,
        biz_with_member: tuple[User, Business],
        booking_for_api: Booking,
        biz_auth_headers: dict,
    ):
        """PDF export returns PDF data."""
        _, biz = biz_with_member

        # Create and complete execution
        create_resp = await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions",
            json={"booking_id": str(booking_for_api.id)},
            headers=biz_auth_headers,
        )
        execution_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/transition",
            json={"target_status": "in_progress"},
            headers=biz_auth_headers,
        )
        await client.post(
            f"/api/v1/businesses/{biz.id}/service-executions/{execution_id}/complete",
            headers=biz_auth_headers,
        )

        # Export PDF
        response = await client.get(
            f"/api/v1/businesses/{biz.id}/ledger/export/pdf",
            headers=biz_auth_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
