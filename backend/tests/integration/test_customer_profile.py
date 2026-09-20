"""Integration tests for customer profile API.

Tests: get profile, update profile, access restrictions.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestCustomerProfileAPI:
    """Test customer profile CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_own_profile(self, client: AsyncClient, test_user, auth_headers):
        """Customer can retrieve their own profile."""
        response = await client.get("/api/v1/customer/profile", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Test"
        assert data["last_name"] == "User"
        assert data["status"] == "incomplete"
        assert "user_id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_update_own_profile(self, client: AsyncClient, test_user, auth_headers):
        """Customer can update their own profile."""
        response = await client.put(
            "/api/v1/customer/profile",
            headers=auth_headers,
            json={
                "phone": "+1234567890",
                "city": "Testville",
                "country": "Testland",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "+1234567890"
        assert data["city"] == "Testville"
        assert data["country"] == "Testland"
        # Unchanged fields remain
        assert data["first_name"] == "Test"

    @pytest.mark.asyncio
    async def test_profile_requires_auth(self, client: AsyncClient):
        """Unauthenticated request to profile returns 401."""
        response = await client.get("/api/v1/customer/profile")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_profile_update_validation(self, client: AsyncClient, test_user, auth_headers):
        """Profile update validates field lengths."""
        response = await client.put(
            "/api/v1/customer/profile",
            headers=auth_headers,
            json={
                "first_name": "A" * 200,  # Too long
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_profile_partial_update(self, client: AsyncClient, test_user, auth_headers):
        """Partial update only changes provided fields."""
        # First set some data
        await client.put(
            "/api/v1/customer/profile",
            headers=auth_headers,
            json={"phone": "111", "city": "Original"},
        )

        # Now update only city
        response = await client.put(
            "/api/v1/customer/profile",
            headers=auth_headers,
            json={"city": "Updated"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["city"] == "Updated"
        assert data["phone"] == "111"  # Unchanged
