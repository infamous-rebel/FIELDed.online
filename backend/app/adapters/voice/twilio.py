"""Twilio Voice provider implementation.

Initiates outbound voice calls through the Twilio REST API.
Phase 14A: call initiation only — no conversational agent.
Translates Twilio API responses and errors into ProviderResult.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider

logger = logging.getLogger(__name__)

_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/"


class TwilioVoiceProvider(VoiceProvider):
    """Voice provider backed by the Twilio Voice API.

    Phase 14A: initiates outbound calls.  TwiML for call
    behavior is served by the callback_url (14B concern).
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
        return "twilio_voice"

    async def initiate_call(
        self, request: VoiceCallRequest
    ) -> ProviderResult:
        """Initiate an outbound call through Twilio.

        Creates a Twilio Call resource.  The call's behavior
        is controlled by the callback_url (TwiML webhook).
        """
        from_number = request.from_number or self._from_number
        url = urljoin(
            self._api_base,
            f"Accounts/{self._account_sid}/Calls.json",
        )

        payload: dict = {
            "To": request.to,
            "From": from_number,
        }

        if request.callback_url:
            payload["Url"] = request.callback_url
            payload["Method"] = request.callback_method

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    data=payload,
                    auth=(self._account_sid, self._auth_token),
                )

            if response.status_code in (200, 201):
                data = response.json()
                call_sid = data.get("sid", "")
                return ProviderResult.ok(
                    provider_reference=call_sid,
                    raw_response={
                        "status": data.get("status"),
                        "status_code": response.status_code,
                    },
                )

            retryable = response.status_code >= 500
            return ProviderResult.failure(
                error=f"Twilio Voice API error: {response.status_code} {response.text[:500]}",
                retryable=retryable,
                raw_response={
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                },
            )

        except httpx.TimeoutException:
            return ProviderResult.failure(
                error="Twilio Voice API timeout",
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult.failure(
                error=f"Twilio Voice API error: {exc}",
                retryable=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Twilio Voice provider")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )
