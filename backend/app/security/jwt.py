"""JWT token creation and validation.

Uses PyJWT for token management. The secret key and algorithm
are configurable via environment variables.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import Settings
from app.exceptions import AuthenticationError


def create_access_token(
    settings: Settings,
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        settings: Application settings with JWT configuration.
        subject: The token subject (typically user ID).
        extra_claims: Additional claims to include.

    Returns:
        The encoded JWT token string.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    claims: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }

    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(settings: Settings, subject: str) -> str:
    """Create a JWT refresh token.

    Args:
        settings: Application settings with JWT configuration.
        subject: The token subject (typically user ID).

    Returns:
        The encoded JWT refresh token string.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    claims: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }

    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(settings: Settings, token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        settings: Application settings with JWT configuration.
        token: The JWT token string.

    Returns:
        The decoded token claims.

    Raises:
        AuthenticationError: If the token is invalid, expired, or revoked.
    """
    from app.security.token_revocation import revocation_store

    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired") from None
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {e}") from e

    # Check if token has been revoked
    jti = claims.get("jti")
    if jti and revocation_store.is_revoked(jti):
        raise AuthenticationError("Token has been revoked")

    return claims
