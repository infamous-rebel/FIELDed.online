"""Vonage SMS provider implementation.

Sends SMS through the Vonage Messages API using JWT authentication.
Translates Vonage API responses and errors into ProviderResult.

The Messages API endpoint is:
    POST https://api.nexmo.com/v1/messages

Vonage returns a ``message_uuid`` on success that can be correlated
with delivery receipt webhooks.
"""

from __future__ import annotations

import logging

import httpx

from app.adapters.common import ProviderResult
from app.adapters.sms.base import SMSMessage, SMSProvider
from app.adapters.vonage.auth import generate_vonage_jwt

logger = logging.getLogger(__name__)

_VONAGE_MESSAGES_API = "https://api.nexmo.com/v1/messages"


class VonageSmsProvider(SMSProvider):
    """SMS provider backed by the Vonage Messages API.

    Uses JWT authentication (Application-based).  The private key
    PEM and application ID are provided at construction time from
    backend-only environment variables.
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
        return "vonage_sms"

    async def send(self, message: SMSMessage) -> ProviderResult:
        """Send an SMS through the Vonage Messages API.

        Network/5xx errors are retryable.  4xx errors are not.
        """
        from_number = message.from_number or self._from_number
        if not self._application_id or not self._private_key_pem:
            logger.warning("Vonage SMS provider selected but credentials are empty.")
            return ProviderResult.failure(
                error="Vonage SMS API credentials not configured",
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
        payload = {
            "channel": "sms",
            "message_type": "text",
            "to": message.to,
            "from": from_number,
            "text": message.body,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._api_base, headers=headers, json=payload)

            if response.status_code in (200, 201, 202):
                data = response.json()
                message_uuid = data.get("message_uuid", "")
                logger.info(
                    "vonage_sms_sent",
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
                error=f"Vonage SMS API error: {response.status_code} {response.text[:500]}",
                retryable=retryable,
                raw_response={
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                },
            )

        except httpx.TimeoutException:
            return ProviderResult.failure(
                error="Vonage SMS API timeout",
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult.failure(
                error=f"Vonage SMS API error: {exc}",
                retryable=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Vonage SMS provider")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )
