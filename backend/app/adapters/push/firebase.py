"""Firebase Cloud Messaging (FCM) push notification provider.

Implements the PushProvider interface using Firebase Cloud Messaging
HTTP v1 API for sending push notifications to mobile devices.

Configuration:
    PUSH_PROVIDER=firebase
    PUSH_API_KEY=<FCM server key or service account JSON path>
    FIREBASE_PROJECT_ID=<Firebase project ID>

The provider sends data-only or notification messages via FCM.
Requires the firebase-admin SDK or direct HTTP API access.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.adapters.common import ProviderResult
from app.adapters.push.base import PushMessage, PushProvider

logger = logging.getLogger(__name__)

_FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


class FirebasePushProvider(PushProvider):
    """Firebase Cloud Messaging push notification provider."""

    def __init__(self, project_id: str, server_key: str) -> None:
        self._project_id = project_id
        self._server_key = server_key

    @property
    def provider_name(self) -> str:
        return "firebase"

    async def send(self, message: PushMessage) -> ProviderResult:
        """Send a push notification via FCM HTTP v1 API.

        Sends a notification message with optional data payload.
        The device_token is the FCM registration token.
        """
        if not self._project_id or not self._server_key:
            logger.warning("Firebase push provider selected but credentials are empty.")
            return ProviderResult.failure(
                error="Firebase push credentials not configured",
                retryable=False,
            )

        url = _FCM_SEND_URL.format(project_id=self._project_id)
        headers = {
            "Authorization": f"key={self._server_key}",
            "Content-Type": "application/json",
        }

        payload = self._build_payload(message)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            message_id = data.get("name", "")
            logger.info(
                "push_sent",
                extra={"device": message.device_token[:16] + "...", "message_id": message_id},
            )
            return ProviderResult(
                success=True,
                provider_reference=message_id or None,
                raw_response=data,
            )

        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text if exc.response else str(exc)
            logger.error(
                "push_send_failed",
                extra={
                    "device": message.device_token[:16] + "...",
                    "status_code": exc.response.status_code if exc.response else None,
                    "body": error_body[:500],
                },
            )
            retryable = exc.response.status_code >= 500 if exc.response else True
            return ProviderResult.failure(
                error=f"FCM error: {exc.response.status_code}" if exc.response else str(exc),
                retryable=retryable,
            )
        except httpx.RequestError as exc:
            logger.error("push_network_error", extra={"error": str(exc)})
            return ProviderResult.failure(
                error=f"FCM network error: {exc}",
                retryable=True,
            )

    def _build_payload(self, message: PushMessage) -> dict[str, Any]:
        """Build the FCM HTTP v1 request payload."""
        fcm_message: dict[str, Any] = {
            "message": {
                "token": message.device_token,
                "notification": {
                    "title": message.title,
                    "body": message.body,
                },
            }
        }

        if message.data:
            # FCM data payload must be string values
            fcm_message["message"]["data"] = {
                k: json.dumps(v) if not isinstance(v, str) else v for k, v in message.data.items()
            }

        return fcm_message
