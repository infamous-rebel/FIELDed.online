"""Distributed rate limiting for API endpoints.

Provides a Redis-backed sliding window rate limiter for multi-instance
deployments. Falls back to in-memory limiting when Redis is unavailable.

Configuration:
    RATE_LIMIT_BACKEND=redis  (or "memory" for single-instance)
    REDIS_URL=redis://...
"""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class RedisSlidingWindowLimiter:
    """Redis-backed sliding window rate limiter.

    Uses a sorted set per key with timestamps as scores.
    Automatically cleans expired entries.
    """

    def __init__(self, redis_url: str, max_requests: int, window_seconds: int) -> None:
        self._redis_url = redis_url
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis: Any = None

    async def _get_redis(self) -> Any:
        """Lazy-initialize the Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            except ImportError:
                logger.warning("redis package not installed. Rate limiting disabled.")
                return None
            except Exception as exc:
                logger.warning("Redis connection failed: %s. Rate limiting disabled.", exc)
                return None
        return self._redis

    async def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed under the rate limit."""
        r = await self._get_redis()
        if r is None:
            return True  # Fail open if Redis unavailable

        try:
            now = time.time()
            window_start = now - self.window_seconds
            redis_key = f"ratelimit:{key}"

            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, self.window_seconds + 10)
            results = await pipe.execute()

            count = results[2]
            if count > self.max_requests:
                # Remove the just-added entry since request is denied
                await r.zrem(redis_key, str(now))
                return False
            return True

        except Exception as exc:
            logger.warning("Redis rate limiter error: %s. Failing open.", exc)
            return True


class DistributedRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with Redis backend support.

    When RATE_LIMIT_BACKEND=redis, uses Redis for distributed limiting.
    Falls back to in-memory limiting otherwise.
    """

    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._settings: Any = None
        self._limiters: dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self, request: Request) -> None:
        """Lazy initialization from app settings."""
        if self._initialized:
            return
        self._initialized = True

        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            return

        self._settings = settings
        backend = getattr(settings, "rate_limit_backend", "memory")
        redis_url = getattr(settings, "redis_url", "")

        # Pre-configured limiters for auth endpoints
        auth_limits = {
            "/api/v1/auth/login": (10, 300),  # 10 per 5 min
            "/api/v1/auth/register": (5, 600),  # 5 per 10 min
            "/api/v1/auth/forgot-password": (3, 900),  # 3 per 15 min
        }

        if backend == "redis" and redis_url:
            for path, (max_req, window) in auth_limits.items():
                self._limiters[path] = RedisSlidingWindowLimiter(
                    redis_url=redis_url, max_requests=max_req, window_seconds=window
                )
            logger.info("Distributed rate limiting enabled (Redis backend)")
        else:
            # Fall back to in-memory limiting
            from app.middleware.rate_limit import SlidingWindowRateLimiter

            for path, (max_req, window) in auth_limits.items():
                self._limiters[path] = SlidingWindowRateLimiter(max_requests=max_req, window_seconds=window)
            logger.info("In-memory rate limiting enabled")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        self._ensure_initialized(request)

        path = request.url.path
        limiter = self._limiters.get(path)

        if limiter is not None and request.method == "POST":
            client_ip = _get_client_ip(request)
            key = f"{path}:{client_ip}"

            if isinstance(limiter, RedisSlidingWindowLimiter):
                allowed = await limiter.is_allowed(key)
            else:
                allowed = limiter.is_allowed(key)

            if not allowed:
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


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, considering proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
