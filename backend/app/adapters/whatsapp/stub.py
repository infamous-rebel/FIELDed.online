"""Stub WhatsApp provider.

This is a valid adapter implementation for environments where
WhatsApp is not configured.  It logs the attempt and returns
a non-retryable failure — it is NOT a fake success.

Domain code treats this the same as any other provider:
the result is a ProviderResult, and the communication attempt
is recorded accordingly.
"""

from __future__ import annotations

import logging

from app.adapters.common import ProviderResult
from app.adapters.whatsapp.base import WhatsAppMessage, WhatsAppProvider

logger = logging.getLogger(__name__)


class StubWhatsAppProvider(WhatsAppProvider):
    """Stub WhatsApp provider for unconfigured environments."""

    @property
    def provider_name(self) -> str:
        return "stub_whatsapp"

    async def send(self, message: WhatsAppMessage) -> ProviderResult:
        """Log the WhatsApp attempt and return failure.

        The stub does not deliver messages.  It records the intent
        so the communication pipeline can track the gap.
        """
        logger.warning(
            "WhatsApp provider is not configured. "
            "Message to %s was not delivered.",
            message.to,
        )
        return ProviderResult.failure(
            error="WhatsApp provider is not configured (stub adapter)",
            retryable=False,
        )
