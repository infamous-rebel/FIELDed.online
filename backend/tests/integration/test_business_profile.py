"""Integration tests for business profile management.

Requires PostgreSQL test database.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User


@pytest.mark.integration
class TestBusinessProfileAPI:
    """Test business profile CRUD operations."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Test Biz", slug=f"test-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(
            user_id=test_user.id, business_id=business.id, role="owner"
        )
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_get_profile_requires_auth(
        self, client: AsyncClient, owner_business: Business
    ):
        response = await client.get(
            f"/api/v1/businesses/{owner_business.id}/profile"
        )
        assert response.status_code == 401

    async def test_get_own_profile(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business: Business,
    ):
        response = await client.get(
            f"/api/v1/businesses/{owner_business.id}/profile",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["public_status"] == "incomplete"

    async def test_update_profile_as_owner(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business: Business,
    ):
        response = await client.put(
            f"/api/v1/businesses/{owner_business.id}/profile",
            headers=auth_headers,
            json={
                "description": "A great business",
                "phone": "+1234567890",
                "social_links": {
                    "website": "https://example.com",
                    "facebook": "https://facebook.com/testbiz",
                },
                "public_status": "active",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "A great business"
        assert data["phone"] == "+1234567890"
        assert data["social_links"]["website"] == "https://example.com"
        assert data["social_links"]["facebook"] == "https://facebook.com/testbiz"
        assert data["public_status"] == "active"

    async def test_rejects_malformed_social_url(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business: Business,
    ):
        response = await client.put(
            f"/api/v1/businesses/{owner_business.id}/profile",
            headers=auth_headers,
            json={
                "social_links": {
                    "website": "javascript:alert(1)",
                },
            },
        )
        assert response.status_code == 422

    async def test_non_member_cannot_get_profile(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        owner_business: Business,
    ):
        response = await client.get(
            f"/api/v1/businesses/{owner_business.id}/profile",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

    async def test_non_member_cannot_update_profile(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        owner_business: Business,
    ):
        response = await client.put(
            f"/api/v1/businesses/{owner_business.id}/profile",
            headers=second_auth_headers,
            json={"description": "hacked"},
        )
        assert response.status_code == 403
