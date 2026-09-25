"""Stub calendar provider for unconfigured environments."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.adapters.calendar.base import (
    CalendarEvent,
    CalendarEventResult,
    CalendarProvider,
)

logger = logging.getLogger(__name__)


class StubCalendarProvider(CalendarProvider):
    """Stub calendar provider — logs intent, returns failure."""

    @property
    def provider_name(self) -> str:
        return "stub_calendar"

    async def create_event(self, event: CalendarEvent) -> CalendarEventResult:
        logger.warning("Calendar provider not configured. Event '%s' not created.", event.title)
        return CalendarEventResult(event_id="", success=False, error="Calendar provider not configured (stub)")

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEventResult:
        logger.warning("Calendar provider not configured. Event %s not updated.", event_id)
        return CalendarEventResult(event_id=event_id, success=False, error="Calendar provider not configured (stub)")

    async def delete_event(self, event_id: str) -> CalendarEventResult:
        logger.warning("Calendar provider not configured. Event %s not deleted.", event_id)
        return CalendarEventResult(event_id=event_id, success=False, error="Calendar provider not configured (stub)")

    async def get_availability(
        self,
        start: datetime,
        end: datetime,
        calendar_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        logger.info("Calendar provider not configured. Returning empty availability.")
        return []
