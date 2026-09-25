"""WhatsApp Business Cloud API provider.

Implements the WhatsAppProvider interface using Meta's
WhatsApp Business Cloud API (graph.facebook.com).

Configuration:
    WHATSAPP_PROVIDER=whatsapp_cloud
    WHATSAPP_API_KEY=<Meta permanent access token>
    WHATSAPP_PHONE_NUMBER_ID=<WhatsApp Business phone number ID>

The provider sends template messages and free-form text messages
through the Cloud API. Message delivery is asynchronous — the API
returns a message ID that can be correlated with webhook status
updates.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.common import ProviderResult
from app.adapters.whatsapp.base import WhatsAppMessage, WhatsAppProvider

logger = logging.getLogger(__name__)

_WHATSAPP_API_VERSION = "v19.0"
_WHATSAPP_BASE_URL = f"https://graph.facebook.com/{_WHATSAPP_API_VERSION}"


class WhatsAppCloudProvider(WhatsAppProvider):
    """WhatsApp Business Cloud API provider."""

    def __init__(self, access_token: str, phone_number_id: str) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id

    @property
    def provider_name(self) -> str:
        return "whatsapp_cloud"

    async def send(self, message: WhatsAppMessage) -> ProviderResult:
        """Send a WhatsApp message via the Cloud API.

        Supports both template messages and free-form text.
        Template messages are required for initiating conversations
        with customers who haven't messaged in the last 24 hours.
        """
        if not self._access_token or not self._phone_number_id:
            logger.warning("WhatsApp Cloud provider selected but credentials are empty.")
            return ProviderResult.failure(
                error="WhatsApp Cloud API credentials not configured",
                retryable=False,
            )

        url = f"{_WHATSAPP_BASE_URL}/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        payload = self._build_payload(message)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            message_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(
                "whatsapp_sent",
                extra={"to": message.to, "message_id": message_id},
            )
            return ProviderResult(
                success=True,
                provider_reference=message_id or None,
                raw_response=data,
            )

        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text if exc.response else str(exc)
            logger.error(
                "whatsapp_send_failed",
                extra={
                    "to": message.to,
                    "status_code": exc.response.status_code if exc.response else None,
                    "body": error_body[:500],
                },
            )
            retryable = exc.response.status_code >= 500 if exc.response else True
            return ProviderResult.failure(
                error=f"WhatsApp Cloud API error: {exc.response.status_code}" if exc.response else str(exc),
                retryable=retryable,
            )
        except httpx.RequestError as exc:
            logger.error("whatsapp_network_error", extra={"to": message.to, "error": str(exc)})
            return ProviderResult.failure(
                error=f"WhatsApp network error: {exc}",
                retryable=True,
            )

    def _build_payload(self, message: WhatsAppMessage) -> dict[str, Any]:
        """Build the Cloud API request payload."""
        base: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": message.to,
        }

        if message.template_name:
            # Template message (for conversation initiation)
            template: dict[str, Any] = {
                "name": message.template_name,
            }
            if message.template_language:
                template["language"] = {"code": message.template_language}
            if message.template_components:
                template["components"] = message.template_components
            base["type"] = "template"
            base["template"] = template
        else:
            # Free-form text message
            base["type"] = "text"
            base["text"] = {"body": message.body}

        return base
