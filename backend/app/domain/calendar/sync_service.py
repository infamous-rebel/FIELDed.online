"""Calendar synchronisation service.

Syncs FIELDed bookings to Google Calendar when a business has an
active calendar connection.

Architecture:
    FIELDed Booking (authoritative)
    → CalendarSyncService
    → Google Calendar Provider (per-business OAuth token)
    → Google Calendar API
    → Sync record (audit trail)

Key invariants:
    - Calendar never changes authoritative FIELDed booking state.
    - Event creation is idempotent (deterministic booking-derived ID).
    - Calendar failure does NOT invalidate the booking.
    - Sync failures are recorded and surfaced to the business.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.calendar.base import CalendarEvent, CalendarProvider
from app.adapters.calendar.google_calendar import GoogleCalendarProvider
from app.adapters.calendar.stub import StubCalendarProvider
from app.domain.booking.models import Booking
from app.domain.calendar.models import CalendarConnection, CalendarEventSyncRecord
from app.domain.calendar.oauth import (
    decrypt_token,
    refresh_access_token,
    token_is_expired,
)
from app.domain.calendar.repository import (
    CalendarConnectionRepository,
    CalendarEventSyncRepository,
)
from app.logging import get_logger

logger = get_logger(__name__)


def _booking_event_id(booking_id: uuid.UUID) -> str:
    """Deterministic FIELDed booking-derived event identifier.

    Retries with the same booking_id produce the same event ID,
    preventing duplicate calendar events.
    """
    return f"fielded-booking-{booking_id}"


class CalendarSyncService:
    """Synchronises FIELDed bookings to a business's Google Calendar.

    The service resolves the calendar provider per-business using the
    stored OAuth token.  Token refresh is handled transparently.
    """

    def __init__(self, session: AsyncSession, *, app_secret: str = "") -> None:
        self.session = session
        self._conn_repo = CalendarConnectionRepository(session)
        self._sync_repo = CalendarEventSyncRepository(session)
        self._app_secret = app_secret

    # --- Public API ---

    async def sync_booking_confirmed(self, booking: Booking) -> CalendarEventSyncRecord | None:
        """Create a calendar event when a booking becomes CONFIRMED.

        Returns the sync record, or None if no active connection exists.
        Does NOT raise on provider failure — records the error instead.
        """
        connection = await self._resolve_active_connection(booking.business_id)
        if connection is None:
            return None

        provider = await self._resolve_provider(connection)
        event = self._build_calendar_event(booking, connection)
        booking_event_id = _booking_event_id(booking.id)

        # Check for existing sync record (idempotency)
        existing = await self._sync_repo.get_by_booking_event_id(booking_event_id)
        if existing and existing.calendar_event_id:
            # Already synced — update instead (handles retries)
            return await self._update_event(provider, existing, event, booking)

        # Create the calendar event
        result = await provider.create_event(event)

        if result.success and result.event_id:
            record = existing or CalendarEventSyncRecord(
                business_id=booking.business_id,
                booking_id=booking.id,
                booking_event_id=booking_event_id,
                provider=connection.provider,
                calendar_id=connection.calendar_id,
            )
            record.calendar_event_id = result.event_id
            record.status = "SYNCED"
            record.last_synced_at = datetime.now(UTC)
            record.last_error = None
            record.attempt_count = (record.attempt_count or 0) + 1
            record.sync_evidence = self._build_evidence(event, result)

            if existing:
                await self._sync_repo.update(record)
            else:
                await self._sync_repo.create(record)

            await self._update_connection_last_synced(connection)

            logger.info(
                "calendar_event_created",
                booking_id=str(booking.id),
                calendar_event_id=result.event_id,
                business_id=str(booking.business_id),
            )
            return record

        # Provider failure — record and surface
        return await self._record_failure(
            booking=booking,
            connection=connection,
            booking_event_id=booking_event_id,
            error=result.error or "Unknown calendar provider error",
            existing=existing,
            event=event,
        )

    async def sync_booking_updated(self, booking: Booking) -> CalendarEventSyncRecord | None:
        """Update the calendar event when a confirmed booking changes.

        Called when a booking's requested_at or other event-relevant
        fields change after initial sync.
        """
        connection = await self._resolve_active_connection(booking.business_id)
        if connection is None:
            return None

        sync_record = await self._sync_repo.get_by_booking(booking.id)
        if sync_record is None or not sync_record.calendar_event_id:
            # Not yet synced — try creating
            return await self.sync_booking_confirmed(booking)

        provider = await self._resolve_provider(connection)
        event = self._build_calendar_event(booking, connection)

        return await self._update_event(provider, sync_record, event, booking)

    async def sync_booking_cancelled(self, booking: Booking) -> CalendarEventSyncRecord | None:
        """Delete/cancel the calendar event when a booking is cancelled.

        The FIELDed booking remains valid regardless of calendar outcome.
        """
        connection = await self._resolve_active_connection(booking.business_id)
        if connection is None:
            return None

        sync_record = await self._sync_repo.get_by_booking(booking.id)
        if sync_record is None or not sync_record.calendar_event_id:
            return None  # Nothing to cancel

        provider = await self._resolve_provider(connection)
        result = await provider.delete_event(sync_record.calendar_event_id)

        if result.success:
            sync_record.status = "CANCELLED"
            sync_record.last_synced_at = datetime.now(UTC)
            sync_record.last_error = None
            await self._sync_repo.update(sync_record)

            logger.info(
                "calendar_event_cancelled",
                booking_id=str(booking.id),
                calendar_event_id=sync_record.calendar_event_id,
                business_id=str(booking.business_id),
            )
        else:
            sync_record.last_error = result.error or "Failed to cancel calendar event"
            sync_record.attempt_count = (sync_record.attempt_count or 0) + 1
            await self._sync_repo.update(sync_record)

            logger.warning(
                "calendar_event_cancel_failed",
                booking_id=str(booking.id),
                error=sync_record.last_error,
                business_id=str(booking.business_id),
            )

        return sync_record

    async def get_sync_status(self, business_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get sync status for all bookings of a business."""
        records = await self._sync_repo.get_by_business(business_id)
        return [
            {
                "booking_id": str(r.booking_id),
                "booking_event_id": r.booking_event_id,
                "calendar_event_id": r.calendar_event_id,
                "status": r.status,
                "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
                "last_error": r.last_error,
                "attempt_count": r.attempt_count,
            }
            for r in records
        ]

    # --- Internal helpers ---

    async def _resolve_active_connection(self, business_id: uuid.UUID) -> CalendarConnection | None:
        """Resolve the active calendar connection for a business."""
        connection = await self._conn_repo.get_by_business(business_id)
        if connection is None or connection.status != "active":
            return None
        return connection

    async def _resolve_provider(self, connection: CalendarConnection) -> CalendarProvider:
        """Build a calendar provider instance using the business's OAuth token.

        Handles transparent token refresh if the access token is expired.
        """
        access_token = await self._ensure_valid_token(connection)
        if not access_token:
            logger.warning(
                "calendar_provider_no_token",
                business_id=str(connection.business_id),
            )
            return StubCalendarProvider()

        return GoogleCalendarProvider(
            api_key=access_token,
            calendar_id=connection.calendar_id,
        )

    async def _ensure_valid_token(self, connection: CalendarConnection) -> str | None:
        """Ensure the connection has a valid access token, refreshing if needed."""
        if not connection.access_token_encrypted or not self._app_secret:
            return None

        access_token = decrypt_token(connection.access_token_encrypted, self._app_secret)

        if not token_is_expired(connection.token_expiry):
            return access_token

        # Token expired — attempt refresh
        if not connection.refresh_token_encrypted:
            return None

        try:
            from app.config import get_settings

            settings = get_settings()
            refresh_token = decrypt_token(connection.refresh_token_encrypted, self._app_secret)

            token_data = await refresh_access_token(
                refresh_token=refresh_token,
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
            )

            # Update stored tokens
            new_access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)

            connection.access_token_encrypted = encrypt_token_safe(new_access_token, self._app_secret)
            connection.token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)
            # Google may issue a new refresh token
            new_refresh = token_data.get("refresh_token")
            if new_refresh:
                connection.refresh_token_encrypted = encrypt_token_safe(new_refresh, self._app_secret)

            await self._conn_repo.update(connection)
            return new_access_token

        except Exception:
            logger.warning(
                "calendar_token_refresh_failed",
                business_id=str(connection.business_id),
                exc_info=True,
            )
            return None

    def _build_calendar_event(self, booking: Booking, connection: CalendarConnection) -> CalendarEvent:
        """Build a CalendarEvent from a FIELDed booking.

        Contains: service name, customer name (where permitted),
        contact information, start/end time, location, booking reference,
        and relevant notes.
        """
        # Duration: default 1 hour if not specified elsewhere
        start = booking.requested_at
        end = start + timedelta(hours=1)

        # Build description with booking reference and notes
        description_parts = [f"FIELDed Booking Reference: {booking.reference}"]
        if booking.notes:
            description_parts.append(f"Notes: {booking.notes}")
        description_parts.append(f"Booking ID: {booking.id}")

        # Customer name from the relationship (if loaded)
        customer_name = None
        customer_email = None
        try:
            customer = booking.customer
            if customer:
                customer_name = (
                    f"{customer.customer_profile.first_name} {customer.customer_profile.last_name}"
                    if customer.customer_profile
                    else None
                )
                customer_email = customer.email
        except Exception:
            pass  # Relationship not loaded — skip

        # Service name from the relationship
        service_name = "Service Booking"
        location = None
        try:
            service_offer = booking.service_offer
            if service_offer:
                service_name = service_offer.name
                if service_offer.delivery_mode:
                    description_parts.append(f"Delivery: {service_offer.delivery_mode}")
        except Exception:
            pass

        # Business name
        business_name = None
        try:
            business = booking.business
            if business:
                business_name = business.name
                # Use business profile address as location if available
                if business.profile:
                    addr_parts = [
                        business.profile.address_line1,
                        business.profile.city,
                        business.profile.postal_code,
                    ]
                    location = ", ".join(p for p in addr_parts if p) or None
        except Exception:
            pass

        # Title: "Service Name — Business Name"
        title = service_name
        if business_name:
            title = f"{service_name} — {business_name}"

        # Build attendees list
        attendees: list[str] = []
        if customer_email:
            attendees.append(customer_email)

        # Full description
        if customer_name:
            description_parts.insert(1, f"Customer: {customer_name}")
        if customer_email:
            description_parts.insert(2, f"Contact: {customer_email}")

        description = "\n".join(description_parts)

        return CalendarEvent(
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            attendees=attendees or None,
            metadata={
                "booking_id": str(booking.id),
                "booking_reference": booking.reference,
                "business_id": str(booking.business_id),
                "customer_id": str(booking.customer_id),
                "source": "FIELDed",
            },
            ical_uid=f"{booking.reference}@fielded.online",
        )

    async def _update_event(
        self,
        provider: CalendarProvider,
        sync_record: CalendarEventSyncRecord,
        event: CalendarEvent,
        booking: Booking,
    ) -> CalendarEventSyncRecord:
        """Update an existing calendar event."""
        result = await provider.update_event(sync_record.calendar_event_id, event)

        if result.success:
            sync_record.status = "SYNCED"
            sync_record.last_synced_at = datetime.now(UTC)
            sync_record.last_error = None
            sync_record.attempt_count = (sync_record.attempt_count or 0) + 1
            sync_record.sync_evidence = self._build_evidence(event, result)
        else:
            sync_record.last_error = result.error or "Failed to update calendar event"
            sync_record.attempt_count = (sync_record.attempt_count or 0) + 1

        await self._sync_repo.update(sync_record)
        return sync_record

    async def _record_failure(
        self,
        *,
        booking: Booking,
        connection: CalendarConnection,
        booking_event_id: str,
        error: str,
        existing: CalendarEventSyncRecord | None,
        event: CalendarEvent,
    ) -> CalendarEventSyncRecord:
        """Record a sync failure without affecting the booking."""
        record = existing or CalendarEventSyncRecord(
            business_id=booking.business_id,
            booking_id=booking.id,
            booking_event_id=booking_event_id,
            provider=connection.provider,
            calendar_id=connection.calendar_id,
        )
        record.status = "FAILED"
        record.last_error = error
        record.attempt_count = (record.attempt_count or 0) + 1
        record.sync_evidence = {"event_title": event.title, "error": error}

        if existing:
            await self._sync_repo.update(record)
        else:
            await self._sync_repo.create(record)

        # Also record on the connection
        connection.last_error = error
        await self._conn_repo.update(connection)

        logger.warning(
            "calendar_sync_failed",
            booking_id=str(booking.id),
            business_id=str(booking.business_id),
            error=error,
            attempt_count=record.attempt_count,
        )
        return record

    async def _update_connection_last_synced(self, connection: CalendarConnection) -> None:
        """Update the connection's last_synced_at timestamp."""
        connection.last_synced_at = datetime.now(UTC)
        await self._conn_repo.update(connection)

    @staticmethod
    def _build_evidence(event: CalendarEvent, result: Any) -> dict[str, Any]:
        """Build sync evidence for audit."""
        return {
            "event_title": event.title,
            "event_start": event.start.isoformat(),
            "event_end": event.end.isoformat(),
            "provider_reference": result.event_id if hasattr(result, "event_id") else None,
            "provider_success": result.success if hasattr(result, "success") else None,
        }


def encrypt_token_safe(plaintext: str, app_secret: str) -> str:
    """Encrypt a token — module-level helper to avoid circular imports."""
    from app.domain.calendar.oauth import encrypt_token

    return encrypt_token(plaintext, app_secret)
