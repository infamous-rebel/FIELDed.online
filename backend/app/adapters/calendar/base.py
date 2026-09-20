"""Calendar provider abstract base class.

Defines the interface for calendar/scheduling integrations.
Concrete implementations can wrap Google Calendar, Outlook, CalDAV, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CalendarEvent:
    """A calendar event."""
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    location: str | None = None
    attendees: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class CalendarEventResult:
    """Result of a calendar operation."""
    event_id: str
    success: bool
    error: str | None = None


class CalendarProvider(ABC):
    """Abstract base class for calendar providers."""

    @abstractmethod
    async def create_event(self, event: CalendarEvent) -> CalendarEventResult:
        """Create a calendar event.

        Args:
            event: The event to create.

        Returns:
            Result with the created event ID.
        """
        ...

    @abstractmethod
    async def update_event(
        self, event_id: str, event: CalendarEvent
    ) -> CalendarEventResult:
        """Update an existing calendar event.

        Args:
            event_id: The event to update.
            event: The updated event data.

        Returns:
            Result of the update.
        """
        ...

    @abstractmethod
    async def delete_event(self, event_id: str) -> CalendarEventResult:
        """Delete a calendar event.

        Args:
            event_id: The event to delete.

        Returns:
            Result of the deletion.
        """
        ...

    @abstractmethod
    async def get_availability(
        self,
        start: datetime,
        end: datetime,
        calendar_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get availability/busy slots in a time range.

        Args:
            start: Range start.
            end: Range end.
            calendar_ids: Optional specific calendars to check.

        Returns:
            List of busy slots.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this calendar provider."""
        ...
