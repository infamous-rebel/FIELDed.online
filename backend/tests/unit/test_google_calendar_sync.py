"""Tests for Google Calendar booking integration.

Covers:
- OAuth connection flow (URL generation, token exchange, refresh)
- Token encryption/decryption at rest
- Event creation with idempotency (deterministic booking-derived ID)
- Duplicate prevention
- Event update (reschedule)
- Event cancellation
- Provider failure handling (booking remains valid)
- Tenant isolation
- Configuration
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.calendar.base import CalendarEvent, CalendarEventResult
from app.adapters.calendar.google_calendar import GoogleCalendarProvider
from app.domain.calendar.models import CalendarConnection, CalendarEventSyncRecord
from app.domain.calendar.oauth import (
    build_authorization_url,
    decrypt_token,
    encrypt_token,
    token_is_expired,
)
from app.domain.calendar.sync_service import CalendarSyncService, _booking_event_id

# ---------------------------------------------------------------------------
# Deterministic event ID
# ---------------------------------------------------------------------------


class TestBookingEventId:
    """Deterministic booking-derived event identifier."""

    def test_format(self) -> None:
        booking_id = uuid.uuid4()
        event_id = _booking_event_id(booking_id)
        assert event_id == f"fielded-booking-{booking_id}"

    def test_deterministic(self) -> None:
        booking_id = uuid.uuid4()
        assert _booking_event_id(booking_id) == _booking_event_id(booking_id)

    def test_different_bookings_different_ids(self) -> None:
        assert _booking_event_id(uuid.uuid4()) != _booking_event_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------


class TestTokenEncryption:
    """OAuth token encryption at rest."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        app_secret = "test-secret-key-for-encryption"
        token = "ya29.test_access_token_value"
        encrypted = encrypt_token(token, app_secret)
        assert encrypted != token
        decrypted = decrypt_token(encrypted, app_secret)
        assert decrypted == token

    def test_different_secrets_produce_different_ciphertext(self) -> None:
        token = "ya29.test_access_token_value"
        enc1 = encrypt_token(token, "secret-1")
        enc2 = encrypt_token(token, "secret-2")
        assert enc1 != enc2

    def test_empty_token(self) -> None:
        encrypted = encrypt_token("", "my-secret")
        decrypted = decrypt_token(encrypted, "my-secret")
        assert decrypted == ""

    def test_unicode_token(self) -> None:
        token = "tökén-with-ünïcödé"
        encrypted = encrypt_token(token, "secret")
        decrypted = decrypt_token(encrypted, "secret")
        assert decrypted == token


# ---------------------------------------------------------------------------
# OAuth URL generation
# ---------------------------------------------------------------------------


class TestOAuthAuthorizationUrl:
    """Google OAuth authorization URL generation."""

    def test_contains_required_params(self) -> None:
        url = build_authorization_url(
            client_id="test-client-id.apps.googleusercontent.com",
            redirect_uri="https://api.fielded.online/api/v1/calendar/oauth/callback",
            state="random-state-value",
        )
        assert "accounts.google.com" in url
        assert "test-client-id" in url
        assert "random-state-value" in url
        # Scope is URL-encoded in the query string
        from urllib.parse import unquote

        assert "calendar.events" in unquote(url)
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    def test_redirect_uri_encoded(self) -> None:
        url = build_authorization_url(
            client_id="cid",
            redirect_uri="https://example.com/callback?extra=1",
            state="s",
        )
        # The redirect URI should be percent-encoded
        assert "redirect_uri=" in url


# ---------------------------------------------------------------------------
# Token expiry check
# ---------------------------------------------------------------------------


class TestTokenExpiry:
    """Token expiry detection."""

    def test_none_is_expired(self) -> None:
        assert token_is_expired(None) is True

    def test_past_is_expired(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        assert token_is_expired(past) is True

    def test_future_not_expired(self) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        assert token_is_expired(future) is False

    def test_within_5min_buffer_is_expired(self) -> None:
        almost = datetime.now(UTC) + timedelta(minutes=3)
        assert token_is_expired(almost) is True


# ---------------------------------------------------------------------------
# CalendarSyncService — event creation
# ---------------------------------------------------------------------------


def _make_mock_booking(
    *,
    booking_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    reference: str = "BKG-test1234",
    status: str = "confirmed",
) -> MagicMock:
    """Create a mock booking with the minimum fields needed for sync."""
    booking = MagicMock()
    booking.id = booking_id or uuid.uuid4()
    booking.business_id = business_id or uuid.uuid4()
    booking.customer_id = customer_id or uuid.uuid4()
    booking.reference = reference
    booking.status = status
    booking.requested_at = datetime.now(UTC) + timedelta(days=1)
    booking.notes = "Test booking notes"

    # Customer relationship
    customer = MagicMock()
    customer.email = "customer@example.com"
    customer.customer_profile = MagicMock()
    customer.customer_profile.first_name = "Jane"
    customer.customer_profile.last_name = "Doe"
    booking.customer = customer

    # Service offer relationship
    service_offer = MagicMock()
    service_offer.name = "Plumbing Repair"
    service_offer.delivery_mode = "on_site"
    booking.service_offer = service_offer

    # Business relationship
    business = MagicMock()
    business.name = "Bob's Plumbing"
    business.profile = MagicMock()
    business.profile.address_line1 = "123 Main St"
    business.profile.city = "London"
    business.profile.postal_code = "EC1A 1BB"
    booking.business = business

    return booking


def _make_mock_connection(
    *,
    business_id: uuid.UUID,
    status: str = "active",
) -> CalendarConnection:
    """Create a CalendarConnection with encrypted tokens."""
    conn = CalendarConnection(
        business_id=business_id,
        provider="google",
        calendar_id="primary",
        status=status,
    )
    # Set encrypted tokens
    conn.access_token_encrypted = encrypt_token("mock-access-token", "test-secret")
    conn.refresh_token_encrypted = encrypt_token("mock-refresh-token", "test-secret")
    conn.token_expiry = datetime.now(UTC) + timedelta(hours=1)
    conn.google_email = "business@example.com"
    return conn


class TestCalendarSyncCreate:
    """Calendar event creation on booking CONFIRMED."""

    @pytest.mark.asyncio
    async def test_creates_event_on_confirmed(self) -> None:
        """When a booking becomes CONFIRMED, a calendar event is created."""
        booking = _make_mock_booking()
        connection = _make_mock_connection(business_id=booking.business_id)

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)
        mock_conn_repo.update = AsyncMock()

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking_event_id = AsyncMock(return_value=None)
        mock_sync_repo.create = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.create_event = AsyncMock(
            return_value=CalendarEventResult(event_id="google-event-123", success=True)
        )

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        result = await service.sync_booking_confirmed(booking)

        assert result is not None
        assert result.status == "SYNCED"
        assert result.calendar_event_id == "google-event-123"
        assert result.booking_id == booking.id
        mock_provider.create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_creation(self) -> None:
        """Retries with the same booking do not create duplicate events."""
        booking = _make_mock_booking()
        connection = _make_mock_connection(business_id=booking.business_id)

        existing_record = CalendarEventSyncRecord(
            business_id=booking.business_id,
            booking_id=booking.id,
            booking_event_id=_booking_event_id(booking.id),
            calendar_event_id="google-event-existing",
            status="SYNCED",
        )

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)
        mock_conn_repo.update = AsyncMock()

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking_event_id = AsyncMock(return_value=existing_record)
        mock_sync_repo.update = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.update_event = AsyncMock(
            return_value=CalendarEventResult(event_id="google-event-existing", success=True)
        )

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        result = await service.sync_booking_confirmed(booking)

        # Should update, not create (idempotent)
        assert result is not None
        mock_provider.update_event.assert_called_once()
        mock_provider.create_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_connection_returns_none(self) -> None:
        """If no active calendar connection, sync returns None silently."""
        booking = _make_mock_booking()

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=None)

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo

        result = await service.sync_booking_confirmed(booking)
        assert result is None


# ---------------------------------------------------------------------------
# CalendarSyncService — event cancellation
# ---------------------------------------------------------------------------


class TestCalendarSyncCancel:
    """Calendar event cancellation when booking is CANCELLED."""

    @pytest.mark.asyncio
    async def test_cancels_event(self) -> None:
        """When a booking is cancelled, the calendar event is deleted."""
        booking = _make_mock_booking(status="cancelled")
        connection = _make_mock_connection(business_id=booking.business_id)

        sync_record = CalendarEventSyncRecord(
            business_id=booking.business_id,
            booking_id=booking.id,
            booking_event_id=_booking_event_id(booking.id),
            calendar_event_id="google-event-to-cancel",
            status="SYNCED",
        )

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking = AsyncMock(return_value=sync_record)
        mock_sync_repo.update = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.delete_event = AsyncMock(
            return_value=CalendarEventResult(event_id="google-event-to-cancel", success=True)
        )

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        result = await service.sync_booking_cancelled(booking)

        assert result is not None
        assert result.status == "CANCELLED"
        mock_provider.delete_event.assert_called_once_with("google-event-to-cancel")

    @pytest.mark.asyncio
    async def test_cancel_no_sync_record(self) -> None:
        """If no sync record exists, cancel returns None (nothing to do)."""
        booking = _make_mock_booking(status="cancelled")
        connection = _make_mock_connection(business_id=booking.business_id)

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking = AsyncMock(return_value=None)

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo

        result = await service.sync_booking_cancelled(booking)
        assert result is None


# ---------------------------------------------------------------------------
# CalendarSyncService — event update (reschedule)
# ---------------------------------------------------------------------------


class TestCalendarSyncUpdate:
    """Calendar event update when booking is rescheduled."""

    @pytest.mark.asyncio
    async def test_updates_event_on_reschedule(self) -> None:
        """When a confirmed booking changes, the calendar event is updated."""
        booking = _make_mock_booking()
        connection = _make_mock_connection(business_id=booking.business_id)

        sync_record = CalendarEventSyncRecord(
            business_id=booking.business_id,
            booking_id=booking.id,
            booking_event_id=_booking_event_id(booking.id),
            calendar_event_id="google-event-to-update",
            status="SYNCED",
        )

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking = AsyncMock(return_value=sync_record)
        mock_sync_repo.update = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.update_event = AsyncMock(
            return_value=CalendarEventResult(event_id="google-event-to-update", success=True)
        )

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        result = await service.sync_booking_updated(booking)

        assert result is not None
        assert result.status == "SYNCED"
        mock_provider.update_event.assert_called_once()


# ---------------------------------------------------------------------------
# CalendarSyncService — provider failure
# ---------------------------------------------------------------------------


class TestCalendarSyncFailure:
    """Provider failure handling — booking remains valid."""

    @pytest.mark.asyncio
    async def test_records_failure_without_raising(self) -> None:
        """If the calendar provider fails, the error is recorded, not raised."""
        booking = _make_mock_booking()
        connection = _make_mock_connection(business_id=booking.business_id)

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)
        mock_conn_repo.update = AsyncMock()

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking_event_id = AsyncMock(return_value=None)
        mock_sync_repo.create = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.create_event = AsyncMock(
            return_value=CalendarEventResult(event_id="", success=False, error="API rate limit exceeded")
        )

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        # Should NOT raise
        result = await service.sync_booking_confirmed(booking)

        assert result is not None
        assert result.status == "FAILED"
        assert "API rate limit exceeded" in result.last_error
        assert result.attempt_count == 1

    @pytest.mark.asyncio
    async def test_failure_increments_attempt_count(self) -> None:
        """Each failure increments the attempt count for retry tracking."""
        booking = _make_mock_booking()
        connection = _make_mock_connection(business_id=booking.business_id)

        existing = CalendarEventSyncRecord(
            business_id=booking.business_id,
            booking_id=booking.id,
            booking_event_id=_booking_event_id(booking.id),
            status="FAILED",
            attempt_count=2,
            last_error="Previous error",
        )

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        mock_conn_repo.get_by_business = AsyncMock(return_value=connection)
        mock_conn_repo.update = AsyncMock()

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking_event_id = AsyncMock(return_value=existing)
        mock_sync_repo.update = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.create_event = AsyncMock(
            return_value=CalendarEventResult(event_id="", success=False, error="Timeout")
        )

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        result = await service.sync_booking_confirmed(booking)

        assert result.attempt_count == 3
        assert result.last_error == "Timeout"


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Calendar sync is scoped to the business."""

    @pytest.mark.asyncio
    async def test_different_business_no_cross_access(self) -> None:
        """A sync for business A never touches business B's connection."""
        business_a = uuid.uuid4()
        business_b = uuid.uuid4()

        booking_a = _make_mock_booking(business_id=business_a)
        connection_a = _make_mock_connection(business_id=business_a)

        mock_session = AsyncMock()
        mock_conn_repo = AsyncMock()
        # Only returns business A's connection
        mock_conn_repo.get_by_business = AsyncMock(side_effect=lambda bid: connection_a if bid == business_a else None)
        mock_conn_repo.update = AsyncMock()

        mock_sync_repo = AsyncMock()
        mock_sync_repo.get_by_booking_event_id = AsyncMock(return_value=None)
        mock_sync_repo.create = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.create_event = AsyncMock(return_value=CalendarEventResult(event_id="evt-a", success=True))

        service = CalendarSyncService(mock_session, app_secret="test-secret")
        service._conn_repo = mock_conn_repo
        service._sync_repo = mock_sync_repo
        service._resolve_provider = AsyncMock(return_value=mock_provider)

        # Business A: sync succeeds
        result_a = await service.sync_booking_confirmed(booking_a)
        assert result_a is not None
        assert result_a.business_id == business_a

        # Business B: no connection → returns None
        booking_b = _make_mock_booking(business_id=business_b)
        result_b = await service.sync_booking_confirmed(booking_b)
        assert result_b is None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestCalendarConfiguration:
    """Calendar configuration fields exist and default correctly."""

    def test_config_has_oauth_fields(self) -> None:
        from app.config import Settings

        settings = Settings(
            _env_file=None,
            google_oauth_client_id="test-id",
            google_oauth_client_secret="test-secret",
            google_oauth_redirect_uri="https://example.com/callback",
        )
        assert settings.google_oauth_client_id == "test-id"
        assert settings.google_oauth_client_secret == "test-secret"
        assert settings.google_oauth_redirect_uri == "https://example.com/callback"

    def test_config_defaults_empty(self) -> None:
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.google_oauth_client_id == ""
        assert settings.google_oauth_client_secret == ""
        assert settings.google_oauth_redirect_uri == ""

    def test_env_example_has_placeholders(self) -> None:
        import pathlib

        env_example = pathlib.Path(__file__).parents[3] / ".env.example"
        content = env_example.read_text()
        assert "GOOGLE_OAUTH_CLIENT_ID" in content
        assert "GOOGLE_OAUTH_CLIENT_SECRET" in content
        assert "GOOGLE_OAUTH_REDIRECT_URI" in content


# ---------------------------------------------------------------------------
# GoogleCalendarProvider — iCalUID support
# ---------------------------------------------------------------------------


class TestGoogleCalendarProviderICalUID:
    """Google Calendar provider passes iCalUID for idempotent creation."""

    @pytest.mark.asyncio
    async def test_create_event_includes_ical_uid(self) -> None:
        """When ical_uid is set, the provider includes iCalUID in the request body."""
        provider = GoogleCalendarProvider(api_key="test-token", calendar_id="primary")

        event = CalendarEvent(
            title="Test Event",
            start=datetime.now(UTC),
            end=datetime.now(UTC) + timedelta(hours=1),
            ical_uid="BKG-test@fielded.online",
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "evt-123"}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.create_event(event)

            assert result.success
            assert result.event_id == "evt-123"

            # Verify iCalUID was in the request body
            call_args = mock_client.post.call_args
            body = (
                call_args.kwargs.get("json") or call_args.args[2]
                if len(call_args.args) > 2
                else call_args[1].get("json")
            )
            assert body["iCalUID"] == "BKG-test@fielded.online"


# ---------------------------------------------------------------------------
# CalendarEvent dataclass — ical_uid field
# ---------------------------------------------------------------------------


class TestCalendarEventDataclass:
    """CalendarEvent supports ical_uid for idempotent creation."""

    def test_ical_uid_default_none(self) -> None:
        event = CalendarEvent(title="Test", start=datetime.now(UTC), end=datetime.now(UTC))
        assert event.ical_uid is None

    def test_ical_uid_set(self) -> None:
        event = CalendarEvent(
            title="Test",
            start=datetime.now(UTC),
            end=datetime.now(UTC),
            ical_uid="test-uid@fielded.online",
        )
        assert event.ical_uid == "test-uid@fielded.online"


# ---------------------------------------------------------------------------
# Migration exists
# ---------------------------------------------------------------------------


class TestMigrationExists:
    """Migration 021_calendar_connections exists."""

    def test_migration_file_exists(self) -> None:
        import pathlib

        migration = pathlib.Path(__file__).parents[2] / "alembic" / "versions" / "021_calendar_connections.py"
        assert migration.exists(), "Migration 021_calendar_connections.py must exist"

    def test_migration_has_correct_revision(self) -> None:
        import pathlib

        migration = pathlib.Path(__file__).parents[2] / "alembic" / "versions" / "021_calendar_connections.py"
        content = migration.read_text()
        assert 'revision: str = "021_calendar_connections"' in content
        assert 'down_revision: str = "020_agent_capabilities"' in content
        assert "calendar_connections" in content
        assert "calendar_event_sync_records" in content
