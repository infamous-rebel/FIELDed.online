"""Unit tests for JWT token management."""

from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.exceptions import AuthenticationError
from app.security.jwt import create_access_token, create_refresh_token, decode_token


def _get_test_settings() -> Settings:
    """Get settings for JWT tests."""
    import os

    os.environ["APP_ENV"] = "development"
    return Settings()


class TestJWTTokens:
    """Test JWT creation and validation."""

    def test_create_and_decode_access_token(self):
        """Access token can be created and decoded."""
        settings = _get_test_settings()
        subject = "user-123"

        token = create_access_token(settings, subject=subject)
        claims = decode_token(settings, token)

        assert claims["sub"] == subject
        assert claims["type"] == "access"
        assert "jti" in claims
        assert "exp" in claims

    def test_create_and_decode_refresh_token(self):
        """Refresh token can be created and decoded."""
        settings = _get_test_settings()
        subject = "user-123"

        token = create_refresh_token(settings, subject=subject)
        claims = decode_token(settings, token)

        assert claims["sub"] == subject
        assert claims["type"] == "refresh"

    def test_extra_claims_included(self):
        """Extra claims are included in the token."""
        settings = _get_test_settings()
        extra = {"business_id": "biz-456", "role": "owner"}

        token = create_access_token(settings, subject="user-123", extra_claims=extra)
        claims = decode_token(settings, token)

        assert claims["business_id"] == "biz-456"
        assert claims["role"] == "owner"

    def test_expired_token_raises(self):
        """Expired tokens raise AuthenticationError."""
        settings = _get_test_settings()
        # Create a token that expires immediately
        settings.jwt_access_token_expire_minutes = 0

        token = create_access_token(settings, subject="user-123")
        # Token should be expired or expiring at the same instant
        time.sleep(0.1)

        with pytest.raises(AuthenticationError, match="expired"):
            decode_token(settings, token)

    def test_invalid_token_raises(self):
        """Invalid tokens raise AuthenticationError."""
        settings = _get_test_settings()

        with pytest.raises(AuthenticationError, match="Invalid token"):
            decode_token(settings, "not.a.valid.token")

    def test_wrong_secret_raises(self):
        """Token signed with wrong secret fails validation."""
        settings1 = _get_test_settings()
        settings2 = _get_test_settings()
        settings2.jwt_secret_key = "different-secret"

        token = create_access_token(settings1, subject="user-123")

        with pytest.raises(AuthenticationError, match="Invalid token"):
            decode_token(settings2, token)
