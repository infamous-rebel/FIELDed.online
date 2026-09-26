"""Calendar integration API endpoints.

Provides the business "Connect Google Calendar" flow:
- Connection status
- OAuth authorization initiation
- OAuth callback (token exchange)
- Calendar listing and selection
- Disconnect
- Sync status

All operations are scoped to a business.  OAuth tokens are stored
encrypted and never exposed through the API.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.calendar.models import CalendarConnection
from app.domain.calendar.oauth import (
    build_authorization_url,
    decrypt_token,
    encrypt_token,
    exchange_authorization_code,
    fetch_user_email,
    list_calendars,
)
from app.domain.calendar.repository import CalendarConnectionRepository
from app.domain.calendar.sync_service import CalendarSyncService
from app.domain.identity.models import User
from app.exceptions import NotFoundError, ValidationError
from app.security.authorization import require_business_member

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CalendarConnectionRead(BaseModel):
    """Calendar connection status (never exposes tokens)."""

    business_id: uuid.UUID
    provider: str
    calendar_id: str
    calendar_summary: str | None = None
    google_email: str | None = None
    status: str
    last_error: str | None = None
    last_synced_at: str | None = None

    model_config = {"from_attributes": True}


class CalendarConnectResponse(BaseModel):
    """Response to a connect request — contains the authorization URL."""

    authorization_url: str
    state: str


class CalendarListEntry(BaseModel):
    """A Google Calendar entry."""

    id: str
    summary: str


class CalendarSelectRequest(BaseModel):
    """Request to select which calendar to sync to."""

    calendar_id: str = Field(..., description="Google Calendar ID to use")


class SyncStatusRead(BaseModel):
    """Sync status for a single booking."""

    booking_id: str
    booking_event_id: str
    calendar_event_id: str | None = None
    status: str
    last_synced_at: str | None = None
    last_error: str | None = None
    attempt_count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connection_to_read(conn: CalendarConnection) -> CalendarConnectionRead:
    """Convert a CalendarConnection to the read schema."""
    return CalendarConnectionRead(
        business_id=conn.business_id,
        provider=conn.provider,
        calendar_id=conn.calendar_id,
        calendar_summary=conn.calendar_summary,
        google_email=conn.google_email,
        status=conn.status,
        last_error=conn.last_error,
        last_synced_at=conn.last_synced_at.isoformat() if conn.last_synced_at else None,
    )


def _get_oauth_settings(request: Request) -> tuple[str, str, str]:
    """Extract Google OAuth settings.  Raises ValidationError if not configured."""
    settings = request.app.state.settings
    client_id = getattr(settings, "google_oauth_client_id", "")
    client_secret = getattr(settings, "google_oauth_client_secret", "")
    redirect_uri = getattr(settings, "google_oauth_redirect_uri", "")
    if not client_id or not client_secret or not redirect_uri:
        raise ValidationError(
            "Google Calendar OAuth is not configured. "
            "Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI."
        )
    return client_id, client_secret, redirect_uri


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/calendar/connection",
    response_model=CalendarConnectionRead | None,
)
async def get_connection_status(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CalendarConnectionRead | None:
    """Get the calendar connection status for a business."""
    repo = CalendarConnectionRepository(db)
    connection = await repo.get_by_business(business_id)
    if connection is None:
        return None
    return _connection_to_read(connection)


# ---------------------------------------------------------------------------
# Connect flow
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/calendar/connect",
    response_model=CalendarConnectResponse,
)
async def initiate_connect(
    business_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CalendarConnectResponse:
    """Initiate the Google Calendar OAuth flow.

    Returns an authorization URL to redirect the user to.
    After authorization, Google redirects to the callback endpoint.
    """
    client_id, _client_secret, redirect_uri = _get_oauth_settings(request)

    # Generate anti-CSRF state
    state = secrets.token_urlsafe(32)

    # Store state → business_id mapping for callback verification
    # (Using a simple in-memory dict for now; production should use Redis)
    request.app.state.setdefault("_calendar_oauth_states", {})[state] = {
        "business_id": str(business_id),
        "user_id": str(user.id),
    }

    authorization_url = build_authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
    )

    return CalendarConnectResponse(authorization_url=authorization_url, state=state)


# ---------------------------------------------------------------------------
# OAuth callback
# ---------------------------------------------------------------------------


@router.get("/calendar/oauth/callback")
async def oauth_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    code: str = Query(...),
    state: str = Query(...),
) -> HTMLResponse:
    """Google OAuth callback — exchanges the authorization code for tokens.

    This is a public endpoint (Google redirects here).
    Validates the state parameter to prevent CSRF.
    """
    client_id, client_secret, redirect_uri = _get_oauth_settings(request)

    # Verify state
    states: dict = request.app.state.get("_calendar_oauth_states", {})
    state_data = states.pop(state, None)
    if state_data is None:
        return HTMLResponse(
            content="<html><body><h1>Calendar Connection Failed</h1>"
            "<p>Invalid or expired authorization state. Please try again.</p></body></html>",
            status_code=400,
        )

    business_id = uuid.UUID(state_data["business_id"])

    # Exchange code for tokens
    try:
        token_data = await exchange_authorization_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
    except ValueError as exc:
        return HTMLResponse(
            content=f"<html><body><h1>Calendar Connection Failed</h1><p>{exc}</p></body></html>",
            status_code=400,
        )

    app_secret = request.app.state.settings.app_secret_key

    # Encrypt tokens
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    from datetime import UTC, datetime, timedelta

    access_encrypted = encrypt_token(access_token, app_secret)
    refresh_encrypted = encrypt_token(refresh_token, app_secret) if refresh_token else None
    token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

    # Fetch user email (non-critical)
    email = await fetch_user_email(access_token=access_token)

    # Create or update connection
    repo = CalendarConnectionRepository(db)
    connection = await repo.get_by_business(business_id)

    if connection is None:
        connection = CalendarConnection(
            business_id=business_id,
            provider="google",
            calendar_id="primary",
            access_token_encrypted=access_encrypted,
            refresh_token_encrypted=refresh_encrypted,
            token_expiry=token_expiry,
            google_email=email,
            status="active",
        )
        await repo.create(connection)
    else:
        connection.access_token_encrypted = access_encrypted
        connection.refresh_token_encrypted = refresh_encrypted
        connection.token_expiry = token_expiry
        connection.google_email = email or connection.google_email
        connection.status = "active"
        connection.last_error = None
        await repo.update(connection)

    return HTMLResponse(
        content=(
            "<html><body style='font-family:system-ui;text-align:center;padding:3rem;'>"
            "<h1>Google Calendar Connected</h1>"
            "<p>Your calendar is now linked to FIELDed.</p>"
            "<p>You can close this window.</p>"
            "<script>if(window.opener){window.opener.postMessage('calendar_connected','*');setTimeout(()=>window.close(),1500)}</script>"
            "</body></html>"
        ),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/calendar/disconnect",
    response_model=dict,
)
async def disconnect_calendar(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    """Disconnect the business's Google Calendar.

    Removes stored tokens and marks the connection as disconnected.
    Existing sync records are preserved for audit.
    """
    repo = CalendarConnectionRepository(db)
    connection = await repo.get_by_business(business_id)
    if connection is None:
        raise NotFoundError("No calendar connection found for this business")

    await repo.delete(connection)

    return {"status": "disconnected", "message": "Google Calendar disconnected successfully"}


# ---------------------------------------------------------------------------
# Calendar listing and selection
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/calendar/calendars",
    response_model=list[CalendarListEntry],
)
async def list_available_calendars(
    business_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CalendarListEntry]:
    """List the business's available Google Calendars.

    Requires an active connection with valid tokens.
    """
    repo = CalendarConnectionRepository(db)
    connection = await repo.get_by_business(business_id)
    if connection is None or connection.status != "active":
        raise ValidationError("No active calendar connection. Connect first.")

    if not connection.access_token_encrypted:
        raise ValidationError("Calendar tokens missing. Reconnect required.")

    app_secret = request.app.state.settings.app_secret_key
    access_token = decrypt_token(connection.access_token_encrypted, app_secret)

    calendars = await list_calendars(access_token=access_token)
    return [CalendarListEntry(id=c["id"], summary=c["summary"]) for c in calendars]


@router.put(
    "/{business_id}/calendar/calendar",
    response_model=CalendarConnectionRead,
)
async def select_calendar(
    business_id: uuid.UUID,
    body: CalendarSelectRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CalendarConnectionRead:
    """Select which Google Calendar to sync bookings to."""
    repo = CalendarConnectionRepository(db)
    connection = await repo.get_by_business(business_id)
    if connection is None or connection.status != "active":
        raise ValidationError("No active calendar connection. Connect first.")

    connection.calendar_id = body.calendar_id
    await repo.update(connection)
    await db.refresh(connection)

    return _connection_to_read(connection)


# ---------------------------------------------------------------------------
# Sync status
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/calendar/sync-status",
    response_model=list[SyncStatusRead],
)
async def get_sync_status(
    business_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SyncStatusRead]:
    """Get calendar sync status for all bookings of a business."""
    app_secret = request.app.state.settings.app_secret_key
    service = CalendarSyncService(db, app_secret=app_secret)
    statuses = await service.get_sync_status(business_id)
    return [SyncStatusRead(**s) for s in statuses]
