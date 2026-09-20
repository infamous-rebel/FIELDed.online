"""Integration tests for the authentication flow.

Tests: register -> login -> access protected route -> refresh token.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient


class TestAuthFlow:
    """Test the complete authentication flow."""

    @pytest.mark.asyncio
    async def test_register_new_customer(self, client: AsyncClient):
        """A new customer can register."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newcustomer@example.com",
                "password": "securepassword123",
                "first_name": "New",
                "last_name": "Customer",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newcustomer@example.com"
        assert data["customer_profile"]["first_name"] == "New"
        assert data["customer_profile"]["last_name"] == "Customer"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_fails(self, client: AsyncClient, test_user):
        """Registering with an existing email fails with 409."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user.email,
                "password": "securepassword123",
                "first_name": "Duplicate",
                "last_name": "User",
            },
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user):
        """Login with correct credentials returns tokens."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        """Login with wrong password returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "wrongpassword"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Login with unknown email returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "password123"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_protected_route(self, client: AsyncClient, auth_headers):
        """Authenticated user can access /me."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data

    @pytest.mark.asyncio
    async def test_protected_route_without_auth(self, client: AsyncClient):
        """Unauthenticated request to /me returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token(self, client: AsyncClient, test_user):
        """Refresh token returns new access and refresh tokens."""
        # Login first
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        refresh_token = login_response.json()["refresh_token"]

        # Refresh
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_register_short_password_fails(self, client: AsyncClient):
        """Password shorter than 8 characters is rejected."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@example.com",
                "password": "short",
                "first_name": "Test",
                "last_name": "User",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint returns 200."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
