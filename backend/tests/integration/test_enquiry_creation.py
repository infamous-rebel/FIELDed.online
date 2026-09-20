"""Integration tests for Enquiry creation and Conversation atomicity.

Requires PostgreSQL test database.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enquiry.models import Conversation, Enquiry
from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User
from app.domain.services.models import ServiceCategory, ServiceOffer


@pytest.mark.integration
class TestEnquiryCreation:
    """Test enquiry creation and conversation atomicity."""

    @pytest_asyncio.fixture
    async def active_business(
        self, db_session: AsyncSession, second_user: User
    ):
        """Create an active business with an active profile and an active service offer.

        second_user is the business owner.
        """
        business = Business(name="Enquiry Biz", slug=f"enquiry-biz-{id(self)}", status="active")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            user_id=second_user.id, business_id=business.id, role="owner"
        )
        db_session.add(member)

        profile = BusinessProfile(
            business_id=business.id,
            public_status="active",
        )
        db_session.add(profile)

        category = ServiceCategory(name="Test Cat", slug=f"test-cat-{id(self)}")
        db_session.add(category)
        await db_session.flush()

        offer = ServiceOffer(
            business_id=business.id,
            name="Test Service",
            slug=f"test-service-{id(self)}",
            status="active",
        )
        db_session.add(offer)
        await db_session.flush()

        return business, offer

    @pytest_asyncio.fixture
    async def inactive_business(
        self, db_session: AsyncSession, second_user: User
    ):
        """Create a business with inactive status."""
        business = Business(name="Inactive Biz", slug=f"inactive-biz-{id(self)}", status="pending")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            user_id=second_user.id, business_id=business.id, role="owner"
        )
        db_session.add(member)

        profile = BusinessProfile(
            business_id=business.id,
            public_status="incomplete",
        )
        db_session.add(profile)
        await db_session.flush()

        return business

    # --- Valid creation ---

    async def test_create_enquiry_as_customer(
        self,
        client: AsyncClient,
        auth_headers: dict,
        active_business,
    ):
        """Authenticated customer can create an enquiry for an active service offer."""
        business, offer = active_business
        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Need this service",
                "message": "I would like to enquire about your service.",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["subject"] == "Need this service"
        assert data["status"] == "submitted"
        assert data["reference"].startswith("ENQ-")
        assert data["business_id"] == str(business.id)
        assert data["service_offer_id"] == str(offer.id)

    async def test_enquiry_creates_conversation_atomically(
        self,
        client: AsyncClient,
        auth_headers: dict,
        active_business,
        db_session: AsyncSession,
    ):
        """Creating an enquiry also creates exactly one conversation."""
        business, offer = active_business
        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Atomic test",
                "message": "Testing atomic creation.",
            },
        )
        assert response.status_code == 201
        enquiry_id = response.json()["id"]

        # Verify conversation exists in DB
        result = await db_session.execute(
            select(Conversation).where(Conversation.enquiry_id == enquiry_id)
        )
        conversation = result.scalar_one_or_none()
        assert conversation is not None
        assert str(conversation.enquiry_id) == enquiry_id

    # --- Invalid service offer ---

    async def test_create_enquiry_invalid_service_offer(
        self,
        client: AsyncClient,
        auth_headers: dict,
        active_business,
    ):
        """Creating an enquiry with a non-existent service offer fails."""
        import uuid
        business, _ = active_business
        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(uuid.uuid4()),
                "subject": "Bad offer",
                "message": "This should fail.",
            },
        )
        assert response.status_code == 404

    async def test_create_enquiry_inactive_service_offer(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        second_user: User,
    ):
        """Creating an enquiry for a DRAFT (inactive) service offer fails."""
        business = Business(name="Draft Biz", slug=f"draft-biz-{id(self)}", status="active")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            user_id=second_user.id, business_id=business.id, role="owner"
        )
        db_session.add(member)

        profile = BusinessProfile(
            business_id=business.id,
            public_status="active",
        )
        db_session.add(profile)

        offer = ServiceOffer(
            business_id=business.id,
            name="Draft Service",
            slug=f"draft-service-{id(self)}",
            status="draft",  # NOT active
        )
        db_session.add(offer)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Draft service",
                "message": "This should fail.",
            },
        )
        assert response.status_code == 422  # ValidationError

    async def test_create_enquiry_service_offer_business_mismatch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        active_business,
        db_session: AsyncSession,
        second_user: User,
    ):
        """Service offer must belong to the referenced business."""
        business, _ = active_business

        # Create a second business with its own offer
        other_biz = Business(name="Other Biz", slug=f"other-biz-{id(self)}", status="active")
        db_session.add(other_biz)
        await db_session.flush()

        other_offer = ServiceOffer(
            business_id=other_biz.id,
            name="Other Service",
            slug=f"other-service-{id(self)}",
            status="active",
        )
        db_session.add(other_offer)
        await db_session.flush()

        # Try to create enquiry on first business with second business's offer
        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(other_offer.id),
                "subject": "Mismatch test",
                "message": "This should fail.",
            },
        )
        assert response.status_code == 404  # Not found (offer doesn't belong to this business)

    # --- Inactive business ---

    async def test_create_enquiry_inactive_business(
        self,
        client: AsyncClient,
        auth_headers: dict,
        inactive_business,
        db_session: AsyncSession,
    ):
        """Creating an enquiry for an inactive business fails."""
        offer = ServiceOffer(
            business_id=inactive_business.id,
            name="Inactive Service",
            slug=f"inactive-svc-{id(self)}",
            status="active",
        )
        db_session.add(offer)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/enquiries/{inactive_business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Inactive biz",
                "message": "This should fail.",
            },
        )
        assert response.status_code == 422  # ValidationError: business not active

    # --- Authentication ---

    async def test_unauthenticated_cannot_create_enquiry(
        self,
        client: AsyncClient,
        active_business,
    ):
        """Unauthenticated requests cannot create enquiries."""
        business, offer = active_business
        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            json={
                "service_offer_id": str(offer.id),
                "subject": "No auth",
                "message": "This should fail.",
            },
        )
        assert response.status_code == 401

    # --- Customer ownership ---

    async def test_customer_can_list_own_enquiries(
        self,
        client: AsyncClient,
        auth_headers: dict,
        active_business,
    ):
        """Customer can list their own enquiries."""
        business, offer = active_business
        # Create an enquiry first
        await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "List test",
                "message": "Testing listing.",
            },
        )

        response = await client.get(
            "/api/v1/enquiries/my-enquiries",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_customer_cannot_access_other_enquiry(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        active_business,
    ):
        """Customer A cannot access Customer B's enquiry."""
        business, offer = active_business

        # test_user creates an enquiry
        create_resp = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Private enquiry",
                "message": "This is mine.",
            },
        )
        enquiry_id = create_resp.json()["id"]

        # second_user tries to access it
        response = await client.get(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403
