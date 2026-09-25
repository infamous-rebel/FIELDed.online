"""CRM provider abstract base class.

Defines the interface for CRM integrations.
Concrete implementations can wrap Salesforce, HubSpot, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ContactSyncRequest:
    """Request to sync a contact to an external CRM."""

    contact_id: str
    name: str
    email: str
    phone: str | None = None
    company: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ContactSyncResult:
    """Result of a CRM sync operation."""

    external_id: str
    success: bool
    provider_name: str
    error: str | None = None


class CRMProvider(ABC):
    """Abstract base class for CRM integrations."""

    @abstractmethod
    async def sync_contact(self, request: ContactSyncRequest) -> ContactSyncResult:
        """Sync a contact to the external CRM.

        Args:
            request: The contact data to sync.

        Returns:
            Result with the external contact ID.
        """
        ...

    @abstractmethod
    async def log_interaction(self, contact_external_id: str, interaction: dict[str, Any]) -> bool:
        """Log an interaction (enquiry, booking, etc.) against a CRM contact.

        Args:
            contact_external_id: The external CRM contact ID.
            interaction: Interaction details (type, subject, body, etc.).

        Returns:
            True if logged successfully.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this CRM provider."""
        ...
