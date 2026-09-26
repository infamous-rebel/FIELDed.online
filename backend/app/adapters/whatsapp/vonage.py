"""Vonage WhatsApp provider implementation.

Sends WhatsApp messages through the Vonage Messages API using JWT
authentication.  Supports both template messages (required for
initiating new conversations) and free-form text (allowed within
the 24-hour customer-service window).

The Messages API endpoint is:
    POST https://api.nexmo.com/v1/messages

Vonage returns a ``message_uuid`` on success that can be correlated
with status webhooks.

WhatsApp template requirements are preserved:
- ``template_name`` must be provided for conversation-initiating messages.
- ``template_components`` carry the template parameters.
- ``template_language`` specifies the locale (default ``en``).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.common import ProviderResult
from app.adapters.vonage.auth import generate_vonage_jwt
from app.adapters.whatsapp.base import WhatsAppMessage, WhatsAppProvider

logger = logging.getLogger(__name__)

_VONAGE_MESSAGES_API = "https://api.nexmo.com/v1/messages"


class VonageWhatsAppProvider(WhatsAppProvider):
    """WhatsApp provider backed by the Vonage Messages API.

    Uses JWT authentication (Application-based).  Template messages
    are required for initiating conversations with customers who
    have not messaged within the 24-hour window.
    """

    def __init__(
        self,
        *,
        application_id: str,
        private_key_pem: str,
        from_number: str,
        api_base: str = _VONAGE_MESSAGES_API,
    ) -> None:
        self._application_id = application_id
        self._private_key_pem = private_key_pem
        self._from_number = from_number
        self._api_base = api_base

    @property
    def provider_name(self) -> str:
        return "vonage_whatsapp"

    async def send(self, message: WhatsAppMessage) -> ProviderResult:
        """Send a WhatsApp message via the Vonage Messages API.

        Supports template and free-form text messages.
        Network/5xx errors are retryable; 4xx are not.
        """
        if not self._application_id or not self._private_key_pem:
            logger.warning("Vonage WhatsApp provider selected but credentials are empty.")
            return ProviderResult.failure(
                error="Vonage WhatsApp API credentials not configured",
                retryable=False,
            )

        token = generate_vonage_jwt(
            application_id=self._application_id,
            private_key_pem=self._private_key_pem,
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(message)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._api_base, headers=headers, json=payload)

            if response.status_code in (200, 201, 202):
                data = response.json()
                message_uuid = data.get("message_uuid", "")
                logger.info(
                    "vonage_whatsapp_sent",
                    extra={"to": message.to, "message_uuid": message_uuid},
                )
                return ProviderResult.ok(
                    provider_reference=message_uuid,
                    raw_response={
                        "status_code": response.status_code,
                        "message_uuid": message_uuid,
                    },
                )

            retryable = response.status_code >= 500
            return ProviderResult.failure(
                error=f"Vonage WhatsApp API error: {response.status_code} {response.text[:500]}",
                retryable=retryable,
                raw_response={
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                },
            )

        except httpx.TimeoutException:
            return ProviderResult.failure(
                error="Vonage WhatsApp API timeout",
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult.failure(
                error=f"Vonage WhatsApp API error: {exc}",
                retryable=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Vonage WhatsApp provider")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )

    def _build_payload(self, message: WhatsAppMessage) -> dict[str, Any]:
        """Build the Vonage Messages API payload for WhatsApp."""
        base: dict[str, Any] = {
            "channel": "whatsapp",
            "message_type": "text",
            "to": message.to,
            "from": self._from_number,
        }

        if message.template_name:
            # Template message — required for conversation initiation.
            # Vonage WhatsApp templates use ``whatsapp`` channel with
            # ``template`` as the message_type.
            base["message_type"] = "template"
            template: dict[str, Any] = {
                "name": message.template_name,
                "language": message.template_language or "en",
            }
            if message.template_components:
                template["parameters"] = message.template_components
            base["template"] = template
        else:
            # Free-form text — only valid within the 24-hour window.
            base["text"] = message.body

        return base
