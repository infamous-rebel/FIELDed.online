"""Performance tests for FIELDed API endpoints.

Measures response times for critical endpoints.
Run with: pytest tests/performance/ -v
Requires a running backend.
"""

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_PERF_TESTS"),
    reason="Performance tests require RUN_PERF_TESTS=1 and a running application",
)

BACKEND_URL = os.environ.get("PERF_BACKEND_URL", "http://localhost:8000")

# Acceptable response time thresholds (seconds)
HEALTH_THRESHOLD = 1.0
PUBLIC_LIST_THRESHOLD = 3.0
AUTH_THRESHOLD = 2.0


class TestPerformanceBenchmarks:
    """Basic performance benchmarks for critical endpoints."""

    def test_health_response_time(self) -> None:
        """Health endpoint responds within threshold."""
        import httpx

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/health")
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < HEALTH_THRESHOLD, f"Health check took {elapsed:.2f}s (threshold: {HEALTH_THRESHOLD}s)"

    def test_public_businesses_response_time(self) -> None:
        """Public businesses endpoint responds within threshold."""
        import httpx

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", params={"limit": 20})
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < PUBLIC_LIST_THRESHOLD, (
            f"Business list took {elapsed:.2f}s (threshold: {PUBLIC_LIST_THRESHOLD}s)"
        )

    def test_service_categories_response_time(self) -> None:
        """Service categories endpoint responds within threshold."""
        import httpx

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/service-categories")
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < HEALTH_THRESHOLD, f"Categories took {elapsed:.2f}s (threshold: {HEALTH_THRESHOLD}s)"

    def test_auth_login_response_time(self) -> None:
        """Auth login endpoint responds within threshold (even on failure)."""
        import httpx

        start = time.monotonic()
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"email": "perf-test@test.com", "password": "testpassword"},
        )
        elapsed = time.monotonic() - start

        assert response.status_code in (401, 404, 200)
        assert elapsed < AUTH_THRESHOLD, f"Auth login took {elapsed:.2f}s (threshold: {AUTH_THRESHOLD}s)"

    def test_concurrent_health_checks(self) -> None:
        """Multiple concurrent health checks all succeed."""
        import concurrent.futures

        import httpx

        def check_health() -> int:
            r = httpx.get(f"{BACKEND_URL}/api/v1/health")
            return r.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_health) for _ in range(10)]
            results = [f.result() for f in futures]

        assert all(code == 200 for code in results), f"Some health checks failed: {results}"
