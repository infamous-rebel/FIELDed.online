"""Vonage Voice provider implementation.

Initiates outbound voice calls through the Vonage Voice API using
JWT authentication.  Integrates with the existing Call Agent
architecture — the Vonage adapter is a drop-in replacement for the
Twilio voice provider at the provider boundary.

The Voice API endpoint is:
    POST https://api.nexmo.com/v1/calls

Vonage returns a call ``uuid`` on success.  Call events (ringing,
answered, completed, etc.) arrive via the ``event_url`` webhook.
Call behaviour is controlled by an NCCO served at ``ncco_url``.

Phase 14C Call Agent architecture is preserved:
- The adapter only initiates calls; conversation governance stays
  in VoiceCallAgent.
- NCCO webhooks replace TwiML webhooks but the agent runtime is
  unchanged.
- Call state progression comes only through provider webhooks.
"""

from __future__ import annotations

import logging

import httpx

from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.adapters.vonage.auth import generate_vonage_jwt

logger = logging.getLogger(__name__)

_VONAGE_VOICE_API = "https://api.nexmo.com/v1/calls"


class VonageVoiceProvider(VoiceProvider):
    """Voice provider backed by the Vonage Voice API.

    Initiates outbound calls.  NCCO for call behaviour is served
    by the callback_url (Phase 14C concern).
    """

    def __init__(
        self,
        *,
        application_id: str,
        private_key_pem: str,
        from_number: str,
        api_base: str = _VONAGE_VOICE_API,
    ) -> None:
        self._application_id = application_id
        self._private_key_pem = private_key_pem
        self._from_number = from_number
        self._api_base = api_base

    @property
    def provider_name(self) -> str:
        return "vonage_voice"

    async def initiate_call(self, request: VoiceCallRequest) -> ProviderResult:
        """Initiate an outbound call through Vonage.

        Creates a Vonage Call resource.  The call's behaviour is
        controlled by the callback_url (NCCO webhook).
        """
        from_number = request.from_number or self._from_number
        if not self._application_id or not self._private_key_pem:
            logger.warning("Vonage Voice provider selected but credentials are empty.")
            return ProviderResult.failure(
                error="Vonage Voice API credentials not configured",
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

        # Build the Vonage Voice API payload
        payload: dict = {
            "to": [{"type": "phone", "number": request.to}],
            "from": {"type": "phone", "number": from_number},
        }

        if request.callback_url:
            # NCCO URL — Vonage fetches call instructions from here
            payload["ncco_url"] = request.callback_url

        # Event webhook — Vonage sends call status updates here
        if request.metadata.get("event_url"):
            payload["event_url"] = [request.metadata["event_url"]]
        elif request.callback_url:
            # Derive event URL from the NCCO URL pattern
            base_ncco = request.callback_url.rsplit("/", 1)[0]
            payload["event_url"] = [f"{base_ncco}/event"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._api_base, headers=headers, json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                call_uuid = data.get("uuid", "")
                logger.info(
                    "vonage_call_initiated",
                    extra={"to": request.to, "call_uuid": call_uuid},
                )
                return ProviderResult.ok(
                    provider_reference=call_uuid,
                    raw_response={
                        "status": data.get("status"),
                        "uuid": call_uuid,
                        "conversation_uuid": data.get("conversation_uuid"),
                        "status_code": response.status_code,
                    },
                )

            retryable = response.status_code >= 500
            return ProviderResult.failure(
                error=f"Vonage Voice API error: {response.status_code} {response.text[:500]}",
                retryable=retryable,
                raw_response={
                    "status_code": response.status_code,
                    "body": response.text[:1000],
                },
            )

        except httpx.TimeoutException:
            return ProviderResult.failure(
                error="Vonage Voice API timeout",
                retryable=True,
            )
        except httpx.HTTPError as exc:
            return ProviderResult.failure(
                error=f"Vonage Voice API error: {exc}",
                retryable=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in Vonage Voice provider")
            return ProviderResult.failure(
                error=f"Unexpected error: {exc}",
                retryable=False,
            )
