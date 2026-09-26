"""Google OAuth helpers and token encryption.

Handles the OAuth 2.0 authorization code flow for Google Calendar:
- Authorization URL generation
- Token exchange (code → access + refresh tokens)
- Token refresh
- Secure token encryption/decryption at rest

Uses the minimum required OAuth scope:
    https://www.googleapis.com/auth/calendar.events
(read/write access to events, NOT calendar management)
"""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Minimum required scope: read/write events only (not calendar list management)
GOOGLE_CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ---------------------------------------------------------------------------
# Token encryption at rest
# ---------------------------------------------------------------------------


def _derive_fernet_key(app_secret: str) -> bytes:
    """Derive a Fernet-compatible key from the application secret."""
    digest = hashlib.sha256(app_secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_token(plaintext: str, app_secret: str) -> str:
    """Encrypt an OAuth token for storage.

    Uses Fernet symmetric encryption when the cryptography package is
    available.  Falls back to base64 encoding (development only) when
    cryptography is not installed.
    """
    try:
        from cryptography.fernet import Fernet

        key = _derive_fernet_key(app_secret)
        f = Fernet(key)
        return f.encrypt(plaintext.encode()).decode()
    except ImportError:
        logger.warning("cryptography package not installed — using base64 encoding for token storage (dev only)")
        return base64.urlsafe_b64encode(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, app_secret: str) -> str:
    """Decrypt an OAuth token from storage."""
    try:
        from cryptography.fernet import Fernet

        key = _derive_fernet_key(app_secret)
        f = Fernet(key)
        return f.decrypt(ciphertext.encode()).decode()
    except ImportError:
        return base64.urlsafe_b64decode(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# OAuth flow helpers
# ---------------------------------------------------------------------------


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Build the Google OAuth 2.0 authorization URL.

    Args:
        client_id: Google OAuth client ID.
        redirect_uri: Registered redirect URI (must match Google Console).
        state: Anti-CSRF random state parameter.

    Returns:
        The full authorization URL to redirect the user to.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_CALENDAR_EVENTS_SCOPE,
        "access_type": "offline",  # Required to receive a refresh token
        "prompt": "consent",  # Ensure refresh token is always provided
        "state": state,
        "include_granted_scopes": "true",
    }
    query = "&".join(f"{k}={_url_encode(v)}" for k, v in params.items())
    return f"{_GOOGLE_AUTH_URL}?{query}"


async def exchange_authorization_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens.

    Returns:
        Dict with: access_token, refresh_token, expires_in, token_type, scope.

    Raises:
        ValueError: If Google returns an error response.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if response.status_code != 200:
        error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        raise ValueError(f"Google token exchange failed: {error_data.get('error', response.status_code)}")

    return response.json()


async def refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Refresh an expired access token using the refresh token.

    Returns:
        Dict with: access_token, expires_in, token_type, scope.
        Note: Google does NOT return a new refresh_token on refresh.

    Raises:
        ValueError: If the refresh token is revoked or invalid.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
        )

    if response.status_code != 200:
        error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        raise ValueError(f"Google token refresh failed: {error_data.get('error', response.status_code)}")

    return response.json()


async def fetch_user_email(
    *,
    access_token: str,
) -> str | None:
    """Fetch the authenticated user's email from Google.

    Returns None on failure (non-critical metadata).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return response.json().get("email")
    except Exception:
        logger.warning("google_userinfo_fetch_failed", exc_info=True)
    return None


async def list_calendars(
    *,
    access_token: str,
) -> list[dict[str, str]]:
    """List the user's Google Calendars.

    Returns a list of dicts with 'id' and 'summary' keys.
    """
    url = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                return [{"id": cal["id"], "summary": cal.get("summary", cal["id"])} for cal in data.get("items", [])]
    except Exception:
        logger.warning("google_calendar_list_failed", exc_info=True)
    return []


def token_is_expired(expiry: datetime | None) -> bool:
    """Check whether an access token has expired (with 5-minute buffer)."""
    if expiry is None:
        return True
    now = datetime.now(UTC)
    return now >= (expiry - timedelta(minutes=5))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _url_encode(value: str) -> str:
    """Percent-encode a URL parameter."""
    from urllib.parse import quote

    return quote(value, safe="")
