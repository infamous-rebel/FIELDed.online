"""Stub push notification provider.

Valid adapter for environments where push is not configured.
Logs the attempt and returns a non-retryable failure.
"""

from __future__ import annotations

import logging

from app.adapters.common import ProviderResult
from app.adapters.push.base import PushMessage, PushProvider

logger = logging.getLogger(__name__)


class StubPushProvider(PushProvider):
    """Stub push provider for unconfigured environments."""

    @property
    def provider_name(self) -> str:
        return "stub_push"

    async def send(self, message: PushMessage) -> ProviderResult:
        """Log the push attempt and return failure."""
        logger.warning(
            "Push provider is not configured. "
            "Notification to device %s was not delivered.",
            message.device_token[:16] + "...",
        )
        return ProviderResult.failure(
            error="Push provider is not configured (stub adapter)",
            retryable=False,
        )
