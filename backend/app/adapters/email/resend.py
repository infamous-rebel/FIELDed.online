"""Resend email provider implementation.

Sends email through the Resend API using httpx for async I/O.
Translates Resend API responses and errors into ProviderResult.
"""

from __future__ import annotations

import logging

import httpx

from app.adapters.common import ProviderResult
from app.adapters.email.base import EmailMessage, EmailProvider

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailProvider(EmailProvider):
    """Email provider backed by the Resend API.

    Uses httpx directly (no Resend SDK dependency) to maintain
    async I/O and provider-agnostic architecture.
    """

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        api_url: str = _RESEND_API_URL,
    ) -> None:
        self._api_key = api_key
        self._from_address = from_address
        self._api_url = api_url

    @property
    def provider_name(self) -> str:
        return "resend"

    async def send(self, message: EmailMessage) -> ProviderResult:
        """Send an email through Resend.

        Translates HTTP errors and API error responses into
        ProviderResult.  Network/5xx errors are retryable.
        """
        from_address = message.from_address or self._from_address

        recipients = (
            message.to if isinstance(message.to, list) else [message.to]
        )

        payload: dict = {
            "from": from_address,
            "to": recipients,
            "subject": message.subject,
        }

        # Prefer HTML body if provided, otherwise use plain text
        if message.html_body:
            payload["html"] = message.html_body
        else:
            payload["text"] = message.body

        if message.reply_to:
            payload["reply_to"] = message.reply_to

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._api_url, json=payload, headers=headers
                )

            if response.status_code == 201 or response.status_code == 200:
                data = response.json()
                message_id = data.get("id", "")
                return ProviderResult.ok(
                    provider_reference=message_id,
                    raw_response={"status_code": response.status_code},
                )

            # 4xx errors are non-retryable
            retryable = response.status_code >= 500
            return ProviderResult.failure(
                error=f"Resend API error: {response.status_code} {response.text[:500]}",
                retryable=retryable,
                raw_response={
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                },
            )

        except httpx.TimeoutException:
            return ProviderResult.failure(
                error="Resend API timeout",
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult.failure(
                error=f"Resend API error: {exc}",
                retryable=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Resend email provider")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )
