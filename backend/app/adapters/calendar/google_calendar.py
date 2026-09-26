"""Google Calendar provider.

Implements the CalendarProvider interface using the Google Calendar API v3.

Configuration:
    CALENDAR_PROVIDER=google
    CALENDAR_API_KEY=<Google service account JSON or API key>
    GOOGLE_CALENDAR_ID=<Primary calendar ID or email>

The provider creates/updates/deletes events and checks availability
in a Google Calendar. Uses the Google Calendar REST API via httpx.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.adapters.calendar.base import (
    CalendarEvent,
    CalendarEventResult,
    CalendarProvider,
)

logger = logging.getLogger(__name__)

_GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar API provider."""

    def __init__(self, api_key: str, calendar_id: str = "primary") -> None:
        self._api_key = api_key
        self._calendar_id = calendar_id

    @property
    def provider_name(self) -> str:
        return "google"

    async def create_event(self, event: CalendarEvent) -> CalendarEventResult:
        """Create a Google Calendar event."""
        if not self._api_key:
            return CalendarEventResult(event_id="", success=False, error="Google Calendar API key not configured")

        url = f"{_GOOGLE_CALENDAR_API}/calendars/{self._calendar_id}/events"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        body: dict[str, Any] = {
            "summary": event.title,
            "start": {"dateTime": event.start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": event.end.isoformat(), "timeZone": "UTC"},
        }
        if event.description:
            body["description"] = event.description
        if event.location:
            body["location"] = event.location
        if event.attendees:
            body["attendees"] = [{"email": a} for a in event.attendees]
        if event.metadata:
            body["extendedProperties"] = {"private": {k: str(v) for k, v in event.metadata.items()}}
        if event.ical_uid:
            body["iCalUID"] = event.ical_uid

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()

            event_id = data.get("id", "")
            logger.info("calendar_event_created", extra={"event_id": event_id})
            return CalendarEventResult(event_id=event_id, success=True)

        except httpx.HTTPStatusError as exc:
            return CalendarEventResult(
                event_id="",
                success=False,
                error=f"Google Calendar API error: {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            return CalendarEventResult(event_id="", success=False, error=f"Network error: {exc}")

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEventResult:
        """Update an existing Google Calendar event."""
        if not self._api_key:
            return CalendarEventResult(event_id=event_id, success=False, error="Google Calendar API key not configured")

        url = f"{_GOOGLE_CALENDAR_API}/calendars/{self._calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        body: dict[str, Any] = {
            "summary": event.title,
            "start": {"dateTime": event.start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": event.end.isoformat(), "timeZone": "UTC"},
        }
        if event.description:
            body["description"] = event.description
        if event.location:
            body["location"] = event.location

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(url, headers=headers, json=body)
                response.raise_for_status()

            return CalendarEventResult(event_id=event_id, success=True)

        except httpx.HTTPStatusError as exc:
            return CalendarEventResult(
                event_id=event_id,
                success=False,
                error=f"Google Calendar API error: {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            return CalendarEventResult(event_id=event_id, success=False, error=f"Network error: {exc}")

    async def delete_event(self, event_id: str) -> CalendarEventResult:
        """Delete a Google Calendar event."""
        if not self._api_key:
            return CalendarEventResult(event_id=event_id, success=False, error="Google Calendar API key not configured")

        url = f"{_GOOGLE_CALENDAR_API}/calendars/{self._calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()

            return CalendarEventResult(event_id=event_id, success=True)

        except httpx.HTTPStatusError as exc:
            return CalendarEventResult(
                event_id=event_id,
                success=False,
                error=f"Google Calendar API error: {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            return CalendarEventResult(event_id=event_id, success=False, error=f"Network error: {exc}")

    async def get_availability(
        self,
        start: datetime,
        end: datetime,
        calendar_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get busy slots from Google Calendar freebusy API."""
        if not self._api_key:
            return []

        url = f"{_GOOGLE_CALENDAR_API}/freeBusy"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        cal_ids = calendar_ids or [self._calendar_id]
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": cid} for cid in cal_ids],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()

            busy_slots: list[dict[str, Any]] = []
            for cal_id, cal_data in data.get("calendars", {}).items():
                for busy in cal_data.get("busy", []):
                    busy_slots.append(
                        {
                            "calendar_id": cal_id,
                            "start": busy.get("start"),
                            "end": busy.get("end"),
                        }
                    )
            return busy_slots

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("calendar_availability_error", extra={"error": str(exc)})
            return []
