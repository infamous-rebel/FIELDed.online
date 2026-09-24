"""Simple rate limiting for API endpoints.

Provides an in-memory sliding window rate limiter.
Suitable for single-instance deployments. For multi-instance,
replace with a Redis-backed implementation.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class SlidingWindowRateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps per key and rejects requests
    that exceed the limit within the window.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed under the rate limit."""
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # Clean old entries
            self._requests[key] = [ts for ts in self._requests[key] if ts > window_start]

            if len(self._requests[key]) >= self.max_requests:
                return False

            self._requests[key].append(now)
            return True

    def reset(self, key: str) -> None:
        """Reset rate limit tracking for a key."""
        with self._lock:
            self._requests.pop(key, None)


# Pre-configured limiters for auth endpoints
auth_login_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=300)  # 10 per 5 min
auth_register_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=600)  # 5 per 10 min
auth_forgot_password_limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=900)  # 3 per 15 min


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, considering proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for sensitive endpoints."""

    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._limiters: dict[str, SlidingWindowRateLimiter] = {
            "/api/v1/auth/login": auth_login_limiter,
            "/api/v1/auth/register": auth_register_limiter,
            "/api/v1/auth/forgot-password": auth_forgot_password_limiter,
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        limiter = self._limiters.get(path)

        if limiter is not None and request.method == "POST":
            client_ip = _get_client_ip(request)
            key = f"{path}:{client_ip}"

            if not limiter.is_allowed(key):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Too many requests. Please try again later.",
                            "details": {},
                            "request_id": getattr(request.state, "request_id", None),
                        }
                    },
                )

        return await call_next(request)
