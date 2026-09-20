"""Unit tests for the sliding window rate limiter."""

from __future__ import annotations

import time

from app.middleware.rate_limit import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    """Tests for the sliding window rate limiter."""

    def test_allows_within_limit(self):
        """Requests within the limit are allowed."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)

        assert limiter.is_allowed("test-key") is True
        assert limiter.is_allowed("test-key") is True
        assert limiter.is_allowed("test-key") is True

    def test_blocks_over_limit(self):
        """Requests over the limit are blocked."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)

        assert limiter.is_allowed("test-key") is True
        assert limiter.is_allowed("test-key") is True
        assert limiter.is_allowed("test-key") is False

    def test_different_keys_independent(self):
        """Different keys have independent limits."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

        assert limiter.is_allowed("key-a") is True
        assert limiter.is_allowed("key-b") is True
        assert limiter.is_allowed("key-a") is False
        assert limiter.is_allowed("key-b") is False

    def test_reset_clears_key(self):
        """Resetting a key allows new requests."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

        assert limiter.is_allowed("test-key") is True
        assert limiter.is_allowed("test-key") is False

        limiter.reset("test-key")
        assert limiter.is_allowed("test-key") is True

    def test_window_expiry(self):
        """Old requests expire after the window."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=1)

        assert limiter.is_allowed("test-key") is True
        assert limiter.is_allowed("test-key") is False

        # Wait for window to expire
        time.sleep(1.1)
        assert limiter.is_allowed("test-key") is True
