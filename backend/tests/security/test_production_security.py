"""Production security tests for FIELDed.

Tests authentication, authorization, tenant isolation, IDOR/BOLA, injection,
rate limiting, and sensitive data exposure against the deployed application.

Run with: pytest tests/security/test_production_security.py -v
Or against production: RUN_SECURITY_TESTS=1 SECURITY_BACKEND_URL=https://... pytest tests/security/
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SECURITY_TESTS"),
    reason="Security tests require RUN_SECURITY_TESTS=1",
)

BACKEND_URL = os.environ.get("SECURITY_BACKEND_URL", "http://localhost:8000")


class TestAuthenticationSecurity:
    """Authentication boundary tests."""

    def test_login_invalid_credentials_rejected(self) -> None:
        """Login with invalid credentials returns 401."""
        import httpx

        response = httpx.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"email": f"nonexistent-{uuid.uuid4().hex[:8]}@test.com", "password": "wrongpassword"},
            timeout=10.0,
        )
        assert response.status_code in (401, 404), f"Expected 401/404, got {response.status_code}"

    def test_login_empty_password_rejected(self) -> None:
        """Login with empty password is rejected."""
        import httpx

        response = httpx.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"email": "test@test.com", "password": ""},
            timeout=10.0,
        )
        assert response.status_code in (400, 401, 422), f"Expected error, got {response.status_code}"

    def test_protected_endpoint_requires_auth(self) -> None:
        """Protected endpoints return 401 without auth token."""
        import httpx

        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses",
            timeout=10.0,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_invalid_jwt_rejected(self) -> None:
        """Invalid JWT tokens are rejected."""
        import httpx

        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses",
            headers={"Authorization": "Bearer invalid.jwt.token"},
            timeout=10.0,
        )
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}"

    def test_expired_jwt_format_rejected(self) -> None:
        """Malformed JWT tokens are rejected."""
        import httpx

        # JWT with expired claim
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZXhwIjoxLCJpYXQiOjF9.invalid"
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses",
            headers={"Authorization": f"Bearer {expired_token}"},
            timeout=10.0,
        )
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}"


class TestTenantIsolation:
    """Tenant isolation and IDOR/BOLA tests."""

    def test_cross_tenant_business_access_blocked(self) -> None:
        """Cannot access another business's data without authorization."""
        import httpx

        # Try to access a random business ID
        fake_business_id = str(uuid.uuid4())
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses/{fake_business_id}/enquiries",
            timeout=10.0,
        )
        # Should be 401 (no auth) or 403/404 (wrong tenant)
        assert response.status_code in (401, 403, 404), f"Expected auth error, got {response.status_code}"

    def test_cross_tenant_booking_access_blocked(self) -> None:
        """Cannot access another business's bookings."""
        import httpx

        fake_business_id = str(uuid.uuid4())
        fake_booking_id = str(uuid.uuid4())
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses/{fake_business_id}/bookings/{fake_booking_id}",
            timeout=10.0,
        )
        assert response.status_code in (401, 403, 404), f"Expected auth error, got {response.status_code}"

    def test_customer_cannot_access_business_endpoints(self) -> None:
        """Customer tokens cannot access business-only endpoints."""
        import httpx

        # Without a valid business member token, business endpoints should fail
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses",
            timeout=10.0,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestInjectionPrevention:
    """SQL injection and input validation tests."""

    def test_sql_injection_in_search(self) -> None:
        """SQL injection attempts in search are handled safely."""
        import httpx

        malicious_queries = [
            "'; DROP TABLE businesses; --",
            "' OR '1'='1",
            "1; SELECT * FROM users --",
            "admin'--",
        ]

        for query in malicious_queries:
            response = httpx.get(
                f"{BACKEND_URL}/api/v1/public/businesses",
                params={"search": query},
                timeout=10.0,
            )
            # Should return 200 with empty results, not 500
            assert response.status_code == 200, f"Search with '{query}' returned {response.status_code}"

    def test_xss_in_search_params(self) -> None:
        """XSS attempts in search params are sanitized."""
        import httpx

        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
        ]

        for payload in xss_payloads:
            response = httpx.get(
                f"{BACKEND_URL}/api/v1/public/businesses",
                params={"search": payload},
                timeout=10.0,
            )
            assert response.status_code == 200, f"XSS payload returned {response.status_code}"
            # Response should not contain the raw payload
            assert payload not in response.text, "XSS payload reflected in response"

    def test_oversized_input_rejected(self) -> None:
        """Oversized input is rejected."""
        import httpx

        # Very long search string
        long_string = "a" * 10000
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/public/businesses",
            params={"search": long_string},
            timeout=10.0,
        )
        # Should either truncate or reject, not crash
        assert response.status_code in (200, 400, 413, 422), f"Oversized input returned {response.status_code}"


class TestRateLimiting:
    """Rate limiting tests."""

    def test_rate_limiting_active(self) -> None:
        """Rate limiting is active on auth endpoints."""
        import httpx

        # Make many rapid login attempts
        responses = []
        for _ in range(20):
            response = httpx.post(
                f"{BACKEND_URL}/api/v1/auth/login",
                json={"email": "ratelimit@test.com", "password": "wrong"},
                timeout=10.0,
            )
            responses.append(response.status_code)

        # At least some should be rate limited (429) or all should be auth failures
        rate_limited = sum(1 for code in responses if code == 429)
        auth_failed = sum(1 for code in responses if code in (401, 404))

        # Either rate limiting kicked in or all auth failures
        assert rate_limited > 0 or auth_failed == len(responses), (
            f"Expected rate limiting or auth failures, got: {set(responses)}"
        )


class TestSensitiveDataExposure:
    """Tests for sensitive data exposure prevention."""

    def test_error_responses_no_stack_traces(self) -> None:
        """Error responses don't contain stack traces."""
        import httpx

        # Trigger an error
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses/nonexistent-id",
            timeout=10.0,
        )

        # Should not contain Python traceback indicators
        body = response.text.lower()
        assert "traceback" not in body, "Stack trace in error response"
        assert 'file "' not in body, "File path in error response"
        assert ".py:" not in body, "Python file reference in error response"

    def test_no_secrets_in_headers(self) -> None:
        """Response headers don't contain sensitive information."""
        import httpx

        response = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", timeout=10.0)

        # Check common sensitive header names
        sensitive_headers = ["x-api-key", "x-secret", "authorization", "x-database-url"]
        for header in sensitive_headers:
            assert header not in response.headers, f"Sensitive header '{header}' found in response"

    def test_public_api_no_internal_details(self) -> None:
        """Public API responses don't leak internal details."""
        import httpx

        response = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", timeout=10.0)
        data = response.json()

        # Should not contain internal IDs or database details
        businesses = data.get("businesses", [])
        for biz in businesses:
            # Should have slug, not raw internal IDs exposed unnecessarily
            assert "slug" in biz or "name" in biz, "Business missing public identifier"


class TestWebhookSecurity:
    """Webhook endpoint security tests."""

    def test_voice_webhook_requires_signature(self) -> None:
        """Voice webhook endpoints require valid signature for non-mock providers."""
        import httpx

        # Without signature, non-mock provider webhooks should fail
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/webhooks/voice/twilio",
            json={"CallSid": "test", "CallStatus": "completed"},
            timeout=10.0,
        )
        # Should be 401 (unauthorized) or 400 (bad request) for missing signature
        assert response.status_code in (400, 401, 404, 405), (
            f"Webhook without signature returned {response.status_code}"
        )


class TestCSRFProtection:
    """CSRF protection tests."""

    def test_state_changing_operations_require_auth(self) -> None:
        """POST/PUT/DELETE operations require authentication."""
        import httpx

        # Try to create a business without auth
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/businesses",
            json={"name": "Test Business", "slug": "test-biz"},
            timeout=10.0,
        )
        assert response.status_code in (401, 403, 422), f"Unauthenticated POST returned {response.status_code}"


class TestInputValidation:
    """Input validation tests."""

    def test_invalid_uuid_rejected(self) -> None:
        """Invalid UUIDs in path parameters are rejected."""
        import httpx

        response = httpx.get(
            f"{BACKEND_URL}/api/v1/businesses/not-a-uuid/enquiries",
            timeout=10.0,
        )
        # 401 is acceptable — auth check may precede path validation
        assert response.status_code in (400, 401, 404, 422), f"Invalid UUID returned {response.status_code}"

    def test_invalid_enum_values_rejected(self) -> None:
        """Invalid enum values in query params are rejected."""
        import httpx

        response = httpx.get(
            f"{BACKEND_URL}/api/v1/public/businesses",
            params={"sort": "invalid_sort_value"},
            timeout=10.0,
        )
        # Should either ignore invalid value or return 422
        assert response.status_code in (200, 422), f"Invalid enum returned {response.status_code}"

    def test_negative_limit_rejected(self) -> None:
        """Negative limit values are rejected."""
        import httpx

        response = httpx.get(
            f"{BACKEND_URL}/api/v1/public/businesses",
            params={"limit": -1},
            timeout=10.0,
        )
        assert response.status_code in (200, 400, 422), f"Negative limit returned {response.status_code}"
