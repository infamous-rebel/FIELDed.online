"""Vonage Application JWT authentication.

Vonage Application-based APIs (Messages API, Voice API) require
a JWT signed with the application's RSA private key (RS256).

The JWT carries:
- ``iat`` — issued-at timestamp
- ``exp`` — expiration (max 24 h; we use 15 min for safety)
- ``jti`` — unique token identifier
- ``application_id`` — the Vonage Application UUID

PyJWT (``>=2.10.0``) is already a project dependency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt


def generate_vonage_jwt(
    *,
    application_id: str,
    private_key_pem: str,
    ttl_seconds: int = 900,
) -> str:
    """Generate a Vonage Application JWT.

    Args:
        application_id: Vonage Application UUID.
        private_key_pem: PEM-encoded RSA private key.
        ttl_seconds: Token lifetime (default 15 minutes).

    Returns:
        Encoded JWT string suitable for ``Authorization: Bearer …``.
    """
    now = datetime.now(UTC)
    payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
        "application_id": application_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")
