"""Integration tests for Service Offer CRUD and lifecycle.

Requires PostgreSQL test database.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User
from app.domain.services.models import ServiceCategory, ServiceOffer


@pytest.mark.integration
class TestServiceOfferAPI:
    """Test service offer CRUD and lifecycle operations."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user with a category."""
        business = Business(name="Offer Biz", slug=f"offer-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            user_id=test_user.id, business_id=business.id, role="owner"
        )
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)

        category = ServiceCategory(name="Testing", slug=f"testing-{id(self)}")
        db_session.add(category)
        await db_session.flush()

        return business, category

    @pytest_asyncio.fixture
    async def staff_business(self, db_session: AsyncSession, second_user: User):
        """Create a business where second_user is staff."""
        business = Business(name="Staff Biz", slug=f"staff-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            user_id=second_user.id, business_id=business.id, role="staff"
        )
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_create_offer_as_owner(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        business, category = owner_business
        response = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={
                "name": "Test Service",
                "description": "A test service",
                "category_id": str(category.id),
                "delivery_mode": "on_site",
                "pricing_model": "fixed",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Service"
        assert data["status"] == "draft"
        assert data["delivery_mode"] == "on_site"

    async def test_list_own_offers(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        business, _ = owner_business
        # Create an offer first
        await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={"name": "Service A"},
        )
        response = await client.get(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_transition_draft_to_active(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        business, _ = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={"name": "Transition Test"},
        )
        offer_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}/transition",
            headers=auth_headers,
            json={"target_status": "active"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_transition_active_to_paused(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        business, _ = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={"name": "Pause Test"},
        )
        offer_id = create_resp.json()["id"]

        # Draft -> Active
        await client.post(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}/transition",
            headers=auth_headers,
            json={"target_status": "active"},
        )

        # Active -> Paused
        response = await client.post(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}/transition",
            headers=auth_headers,
            json={"target_status": "paused"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    async def test_invalid_transition_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        business, _ = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={"name": "Invalid Transition"},
        )
        offer_id = create_resp.json()["id"]

        # Draft -> Paused is not allowed
        response = await client.post(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}/transition",
            headers=auth_headers,
            json={"target_status": "paused"},
        )
        assert response.status_code == 422  # StateTransitionError

    async def test_archived_is_terminal(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        business, _ = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={"name": "Archive Test"},
        )
        offer_id = create_resp.json()["id"]

        # Draft -> Archived
        await client.post(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}/transition",
            headers=auth_headers,
            json={"target_status": "archived"},
        )

        # Archived -> Active should fail
        response = await client.post(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}/transition",
            headers=auth_headers,
            json={"target_status": "active"},
        )
        assert response.status_code == 422

    async def test_staff_cannot_create_offer(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        staff_business,
    ):
        response = await client.post(
            f"/api/v1/businesses/{staff_business.id}/offers",
            headers=second_auth_headers,
            json={"name": "Staff Attempt"},
        )
        assert response.status_code == 403

    async def test_non_member_cannot_create_offer(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        owner_business,
    ):
        business, _ = owner_business
        response = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=second_auth_headers,
            json={"name": "Intruder Offer"},
        )
        assert response.status_code == 403

    async def test_cross_business_offer_access_denied(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        owner_business,
    ):
        """Business A's offer cannot be accessed by Business B's member."""
        business, _ = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/offers",
            headers=auth_headers,
            json={"name": "Private Service"},
        )
        offer_id = create_resp.json()["id"]

        # second_user tries to access it
        response = await client.get(
            f"/api/v1/businesses/{business.id}/offers/{offer_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403
