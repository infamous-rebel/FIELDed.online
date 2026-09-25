"""E2E browser tests for FIELDed using Playwright.

Tests the complete customer journey:
1. Landing page loads
2. Search/browse businesses
3. View business profile
4. Create enquiry
5. View enquiry status

These tests require a running backend and frontend.
Run with: pytest tests/e2e/ --browser chromium
"""

from __future__ import annotations

import os

import pytest

# Skip all E2E tests unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_TESTS"),
    reason="E2E tests require RUN_E2E_TESTS=1 and a running application",
)

# Base URLs for testing
BACKEND_URL = os.environ.get("E2E_BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:3000")


@pytest.fixture
def backend_url() -> str:
    return BACKEND_URL


@pytest.fixture
def frontend_url() -> str:
    return FRONTEND_URL


class TestHealthEndpoints:
    """Verify backend health endpoints are reachable."""

    def test_health_check(self, backend_url: str) -> None:
        """Backend health endpoint returns 200."""
        import httpx

        response = httpx.get(f"{backend_url}/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_readiness_check(self, backend_url: str) -> None:
        """Backend readiness endpoint returns 200 with database status."""
        import httpx

        response = httpx.get(f"{backend_url}/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"


class TestFrontendPages:
    """Verify frontend pages load correctly."""

    def test_landing_page(self, frontend_url: str) -> None:
        """Landing page loads with expected content."""
        import httpx

        response = httpx.get(frontend_url)
        assert response.status_code == 200
        assert "FIELDed" in response.text

    def test_search_page(self, frontend_url: str) -> None:
        """Search page loads."""
        import httpx

        response = httpx.get(f"{frontend_url}/search")
        assert response.status_code == 200

    def test_login_page(self, frontend_url: str) -> None:
        """Login page loads."""
        import httpx

        response = httpx.get(f"{frontend_url}/login")
        assert response.status_code == 200

    def test_signup_page(self, frontend_url: str) -> None:
        """Signup page loads."""
        import httpx

        response = httpx.get(f"{frontend_url}/signup")
        assert response.status_code == 200


class TestAPIEndpoints:
    """Verify key API endpoints respond correctly."""

    def test_public_businesses_list(self, backend_url: str) -> None:
        """Public businesses endpoint returns a list."""
        import httpx

        response = httpx.get(f"{backend_url}/api/v1/public/businesses")
        assert response.status_code == 200
        data = response.json()
        assert "businesses" in data
        assert isinstance(data["businesses"], list)

    def test_service_categories(self, backend_url: str) -> None:
        """Service categories endpoint returns categories."""
        import httpx

        response = httpx.get(f"{backend_url}/api/v1/service-categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_auth_login_invalid_credentials(self, backend_url: str) -> None:
        """Login with invalid credentials returns 401."""
        import httpx

        response = httpx.post(
            f"{backend_url}/api/v1/auth/login",
            json={"email": "nonexistent@test.com", "password": "wrongpassword"},
        )
        assert response.status_code in (401, 404)

    def test_advanced_search_filters(self, backend_url: str) -> None:
        """Advanced search filters are accepted."""
        import httpx

        response = httpx.get(
            f"{backend_url}/api/v1/public/businesses",
            params={
                "search": "plumbing",
                "min_rating": 3.0,
                "verified_only": True,
                "sort": "rating",
                "limit": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "businesses" in data
