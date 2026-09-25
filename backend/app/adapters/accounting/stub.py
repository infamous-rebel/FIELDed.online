"""Stub accounting provider for unconfigured environments."""

from __future__ import annotations

import logging

from app.adapters.accounting.base import (
    AccountingProvider,
    InvoiceSyncRequest,
    InvoiceSyncResult,
)

logger = logging.getLogger(__name__)


class StubAccountingProvider(AccountingProvider):
    """Stub accounting provider — logs intent, returns failure."""

    @property
    def provider_name(self) -> str:
        return "stub_accounting"

    async def sync_invoice(self, request: InvoiceSyncRequest) -> InvoiceSyncResult:
        logger.warning(
            "Accounting provider not configured. Invoice %s sync skipped.",
            request.invoice_id,
        )
        return InvoiceSyncResult(
            external_id="",
            success=False,
            provider_name=self.provider_name,
            error="Accounting provider not configured (stub adapter)",
        )

    async def get_sync_status(self, external_id: str) -> dict:
        return {"external_id": external_id, "status": "not_synced"}
