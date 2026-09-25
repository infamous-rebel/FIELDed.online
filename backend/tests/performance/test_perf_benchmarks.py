"""Performance tests for FIELDed API endpoints.

Measures response times and concurrency for critical production paths.
Run with: pytest tests/performance/ -v
Or against production: RUN_PERF_TESTS=1 PERF_BACKEND_URL=https://fielded-api-... pytest tests/performance/
"""

from __future__ import annotations

import concurrent.futures
import os
import statistics
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_PERF_TESTS"),
    reason="Performance tests require RUN_PERF_TESTS=1 and a running application",
)

BACKEND_URL = os.environ.get("PERF_BACKEND_URL", "http://localhost:8000")

# Acceptable response time thresholds (seconds)
# Production thresholds are more lenient due to network latency
HEALTH_THRESHOLD = 2.0
PUBLIC_LIST_THRESHOLD = 5.0
SEARCH_THRESHOLD = 5.0
AUTH_THRESHOLD = 3.0
CONCURRENT_THRESHOLD = 10.0


class TestPerformanceBenchmarks:
    """Basic performance benchmarks for critical endpoints."""

    def test_health_response_time(self) -> None:
        """Health endpoint responds within threshold."""
        import httpx

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/health", timeout=10.0)
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        print(f"\n  Health check: {elapsed:.3f}s")
        assert elapsed < HEALTH_THRESHOLD, f"Health check took {elapsed:.2f}s (threshold: {HEALTH_THRESHOLD}s)"

    def test_public_businesses_response_time(self) -> None:
        """Public businesses endpoint responds within threshold."""
        import httpx

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", params={"limit": 20}, timeout=10.0)
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        print(f"\n  Business list: {elapsed:.3f}s")
        assert elapsed < PUBLIC_LIST_THRESHOLD, (
            f"Business list took {elapsed:.2f}s (threshold: {PUBLIC_LIST_THRESHOLD}s)"
        )

    def test_service_categories_response_time(self) -> None:
        """Service categories endpoint responds within threshold."""
        import httpx

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/categories", timeout=10.0)
        elapsed = time.monotonic() - start

        assert response.status_code == 200, f"Categories returned {response.status_code}"
        print(f"\n  Categories: {elapsed:.3f}s")
        assert elapsed < HEALTH_THRESHOLD, f"Categories took {elapsed:.2f}s (threshold: {HEALTH_THRESHOLD}s)"

    def test_auth_login_response_time(self) -> None:
        """Auth login endpoint responds within threshold (even on failure)."""
        import httpx

        start = time.monotonic()
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"email": "perf-test@test.com", "password": "testpassword"},
            timeout=10.0,
        )
        elapsed = time.monotonic() - start

        assert response.status_code in (401, 404, 200, 429), f"Login returned {response.status_code}"
        print(f"\n  Auth login: {elapsed:.3f}s")
        assert elapsed < AUTH_THRESHOLD, f"Auth login took {elapsed:.2f}s (threshold: {AUTH_THRESHOLD}s)"


class TestConcurrencyBenchmarks:
    """Concurrency tests for production paths."""

    def test_concurrent_health_checks(self) -> None:
        """Multiple concurrent health checks all succeed."""
        import httpx

        def check_health() -> tuple[int, float]:
            start = time.monotonic()
            r = httpx.get(f"{BACKEND_URL}/api/v1/health", timeout=10.0)
            elapsed = time.monotonic() - start
            return r.status_code, elapsed

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_health) for _ in range(10)]
            results = [f.result() for f in futures]

        statuses = [r[0] for r in results]
        times = [r[1] for r in results]

        assert all(code == 200 for code in statuses), f"Some health checks failed: {statuses}"
        print(f"\n  Concurrent health: avg={statistics.mean(times):.3f}s, max={max(times):.3f}s")

    def test_concurrent_business_list(self) -> None:
        """Multiple concurrent business list requests."""
        import httpx

        def fetch_businesses() -> tuple[int, float]:
            start = time.monotonic()
            r = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", timeout=10.0)
            elapsed = time.monotonic() - start
            return r.status_code, elapsed

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_businesses) for _ in range(5)]
            results = [f.result() for f in futures]

        statuses = [r[0] for r in results]
        times = [r[1] for r in results]

        assert all(code == 200 for code in statuses), f"Some requests failed: {statuses}"
        print(f"\n  Concurrent businesses: avg={statistics.mean(times):.3f}s, max={max(times):.3f}s")
        assert max(times) < CONCURRENT_THRESHOLD, f"Max concurrent time {max(times):.2f}s exceeds threshold"


class TestSearchPerformance:
    """Search and discovery performance tests."""

    def test_search_with_filters(self) -> None:
        """Search with multiple filters performs acceptably."""
        import httpx

        start = time.monotonic()
        response = httpx.get(
            f"{BACKEND_URL}/api/v1/public/businesses",
            params={
                "search": "plumbing",
                "min_rating": 3.0,
                "verified_only": True,
                "sort": "rating",
                "limit": 10,
            },
            timeout=10.0,
        )
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        print(f"\n  Filtered search: {elapsed:.3f}s")
        assert elapsed < SEARCH_THRESHOLD, f"Filtered search took {elapsed:.2f}s"

    def test_discovery_search(self) -> None:
        """Discovery search endpoint performance."""
        import httpx

        start = time.monotonic()
        response = httpx.post(
            f"{BACKEND_URL}/api/v1/discovery/search",
            json={"query": "plumber in London"},
            timeout=30.0,
        )
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        print(f"\n  Discovery search: {elapsed:.3f}s")
        # Discovery may take longer due to AI processing
        assert elapsed < 15.0, f"Discovery took {elapsed:.2f}s"


class TestProductionPaths:
    """Tests for critical production API paths."""

    def test_public_business_detail(self) -> None:
        """Public business detail endpoint performance."""
        import httpx

        # First get a business slug
        list_response = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", params={"limit": 1}, timeout=10.0)
        if list_response.status_code != 200:
            pytest.skip("Could not fetch businesses")

        data = list_response.json()
        businesses = data.get("businesses", [])
        if not businesses:
            pytest.skip("No businesses available")

        slug = businesses[0]["slug"]

        start = time.monotonic()
        response = httpx.get(f"{BACKEND_URL}/api/v1/public/business/{slug}", timeout=10.0)
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        print(f"\n  Business detail: {elapsed:.3f}s")
        assert elapsed < PUBLIC_LIST_THRESHOLD, f"Business detail took {elapsed:.2f}s"

    def test_rate_limiting_response(self) -> None:
        """Rate limiting doesn't significantly impact performance."""
        import httpx

        times = []
        for _ in range(5):
            start = time.monotonic()
            response = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", timeout=10.0)
            elapsed = time.monotonic() - start
            times.append(elapsed)
            assert response.status_code == 200

        avg_time = statistics.mean(times)
        print(f"\n  Rate limit test: avg={avg_time:.3f}s over 5 requests")
        assert avg_time < PUBLIC_LIST_THRESHOLD, f"Avg time {avg_time:.2f}s exceeds threshold"


class TestPerformanceReport:
    """Generate a performance report."""

    def test_performance_summary(self) -> None:
        """Run all critical paths and generate summary."""
        import httpx

        results = {}

        # Health
        start = time.monotonic()
        r = httpx.get(f"{BACKEND_URL}/api/v1/health", timeout=10.0)
        results["health"] = {"status": r.status_code, "time": time.monotonic() - start}

        # Businesses
        start = time.monotonic()
        r = httpx.get(f"{BACKEND_URL}/api/v1/public/businesses", timeout=10.0)
        results["businesses"] = {"status": r.status_code, "time": time.monotonic() - start}

        # Categories
        start = time.monotonic()
        r = httpx.get(f"{BACKEND_URL}/api/v1/categories", timeout=10.0)
        results["categories"] = {"status": r.status_code, "time": time.monotonic() - start}

        # Print summary
        print("\n=== Performance Summary ===")
        for name, data in results.items():
            print(f"  {name}: {data['time']:.3f}s (status: {data['status']})")

        # All should succeed (429 on categories is acceptable under rate limiting)
        assert all(d["status"] in (200, 429) for d in results.values()), "Some endpoints failed"
