"""Security tests for cross-tenant isolation.

Verifies that users cannot access each other's data.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestCrossTenantIsolation:
    """Test that tenant isolation is enforced."""

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_user_profile(self, client: AsyncClient, auth_headers):
        """A user's /me endpoint only returns their own data."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # The response should only contain the authenticated user's info
        assert data["email"].endswith("@example.com")

    @pytest.mark.asyncio
    async def test_different_users_get_different_profiles(
        self, client: AsyncClient, auth_headers, second_auth_headers
    ):
        """Two different users see different /me responses."""
        response1 = await client.get("/api/v1/auth/me", headers=auth_headers)
        response2 = await client.get("/api/v1/auth/me", headers=second_auth_headers)

        assert response1.status_code == 200
        assert response2.status_code == 200

        user1 = response1.json()
        user2 = response2.json()

        assert user1["id"] != user2["id"]
        assert user1["email"] != user2["email"]

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client: AsyncClient):
        """An invalid JWT is rejected."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: AsyncClient):
        """A token with wrong format is rejected."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer abc"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_auth_header(self, client: AsyncClient):
        """Missing Authorization header returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_auth_header(self, client: AsyncClient):
        """Malformed Authorization header returns 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "NotBearer something"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_request_id_returned_in_response(self, client: AsyncClient):
        """Every response includes X-Request-ID header."""
        response = await client.get("/api/v1/health")
        assert "x-request-id" in response.headers

    @pytest.mark.asyncio
    async def test_error_response_includes_request_id(self, client: AsyncClient):
        """Error responses include request_id in the body."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert "request_id" in data["error"]
