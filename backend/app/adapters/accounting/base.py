"""Accounting provider abstract base class.

Defines the interface for accounting/bookkeeping integrations.
Concrete implementations can wrap Xero, QuickBooks, FreshBooks, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class InvoiceSyncRequest:
    """Request to sync an invoice to an external accounting system."""

    invoice_id: str
    customer_name: str
    customer_email: str
    amount: str
    currency: str
    description: str
    invoice_date: date
    due_date: date | None = None
    line_items: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class InvoiceSyncResult:
    """Result of an accounting sync operation."""

    external_id: str
    success: bool
    provider_name: str
    error: str | None = None


class AccountingProvider(ABC):
    """Abstract base class for accounting integrations."""

    @abstractmethod
    async def sync_invoice(self, request: InvoiceSyncRequest) -> InvoiceSyncResult:
        """Sync an invoice to the external accounting system.

        Args:
            request: The invoice data to sync.

        Returns:
            Result with the external invoice ID.
        """
        ...

    @abstractmethod
    async def get_sync_status(self, external_id: str) -> dict[str, Any]:
        """Get the sync status of an externally-tracked invoice.

        Args:
            external_id: The external system's invoice ID.

        Returns:
            Status information about the external invoice.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this accounting provider."""
        ...
