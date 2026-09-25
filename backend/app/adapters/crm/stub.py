"""Stub CRM provider for unconfigured environments."""

from __future__ import annotations

import logging
from typing import Any

from app.adapters.crm.base import (
    ContactSyncRequest,
    ContactSyncResult,
    CRMProvider,
)

logger = logging.getLogger(__name__)


class StubCRMProvider(CRMProvider):
    """Stub CRM provider — logs intent, returns failure."""

    @property
    def provider_name(self) -> str:
        return "stub_crm"

    async def sync_contact(self, request: ContactSyncRequest) -> ContactSyncResult:
        logger.warning(
            "CRM provider not configured. Contact %s sync skipped.",
            request.contact_id,
        )
        return ContactSyncResult(
            external_id="",
            success=False,
            provider_name=self.provider_name,
            error="CRM provider not configured (stub adapter)",
        )

    async def log_interaction(self, contact_external_id: str, interaction: dict[str, Any]) -> bool:
        logger.warning(
            "CRM provider not configured. Interaction for %s skipped.",
            contact_external_id,
        )
        return False
