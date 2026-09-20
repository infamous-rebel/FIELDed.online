"""Twilio SMS provider implementation.

Sends SMS through the Twilio REST API using httpx for async I/O.
Translates Twilio API responses and errors into ProviderResult.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

from app.adapters.common import ProviderResult
from app.adapters.sms.base import SMSMessage, SMSProvider

logger = logging.getLogger(__name__)

_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/"


class TwilioSmsProvider(SMSProvider):
    """SMS provider backed by the Twilio Messaging API.

    Uses httpx directly to maintain async I/O and avoid
    importing the Twilio SDK into the domain layer.
    """

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        api_base: str = _TWILIO_API_BASE,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._api_base = api_base

    @property
    def provider_name(self) -> str:
        return "twilio_sms"

    async def send(self, message: SMSMessage) -> ProviderResult:
        """Send an SMS through Twilio.

        Translates HTTP errors and API error responses into
        ProviderResult.  Network/5xx errors are retryable.
        """
        from_number = message.from_number or self._from_number
        url = urljoin(
            self._api_base,
            f"Accounts/{self._account_sid}/Messages.json",
        )

        payload = {
            "To": message.to,
            "From": from_number,
            "Body": message.body,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    data=payload,
                    auth=(self._account_sid, self._auth_token),
                )

            if response.status_code in (200, 201):
                data = response.json()
                sid = data.get("sid", "")
                return ProviderResult.ok(
                    provider_reference=sid,
                    raw_response={
                        "status": data.get("status"),
                        "status_code": response.status_code,
                    },
                )

            # 4xx are non-retryable, 5xx are retryable
            retryable = response.status_code >= 500
            return ProviderResult.failure(
                error=f"Twilio SMS API error: {response.status_code} {response.text[:500]}",
                retryable=retryable,
                raw_response={
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                },
            )

        except httpx.TimeoutException:
            return ProviderResult.failure(
                error="Twilio SMS API timeout",
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult.failure(
                error=f"Twilio SMS API error: {exc}",
                retryable=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Twilio SMS provider")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )
