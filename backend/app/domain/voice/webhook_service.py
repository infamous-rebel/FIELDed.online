"""Voice provider webhook processing.

Receives provider callbacks for voice calls and synchronizes call
state idempotently:

- Events are persisted in the existing ``communication_webhooks``
  store (single provider-event store for all channels) with a unique
  (provider, external_event_id) constraint — replays are detected
  and never processed twice.
- Call resolution is by provider reference (CallSid), unscoped by
  business: provider callbacks are system-authority events.  The
  resolved call's business ownership is preserved on the webhook row
  via ``voice_call_id``.
- State changes flow exclusively through the deterministic provider
  orchestration layer — a webhook can never invent a call state.
- Every significant state transition is audited; raw provider
  acknowledgments ("queued") are persisted for provenance only.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.enums import AuditEventType
from app.domain.communication.models import (
    CommunicationAuditEvent,
    CommunicationWebhook,
)
from app.domain.communication.repository import AuditRepository, WebhookRepository
from app.domain.voice.models import VoiceCall, VoiceCallAttempt
from app.domain.voice.provider_service import (
    PROVIDER_NOOP_STATUSES,
    PROVIDER_STATUS_TRANSITIONS,
    VoiceProviderOrchestrationService,
)
from app.exceptions import DomainError

logger = logging.getLogger(__name__)

_AUDIT_CHANNEL = "VOICE"

_SIGNATURE_HEADERS = ("x-voice-signature", "x-twilio-signature")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _header_value(headers, name: str) -> str | None:
    """Case-insensitive header lookup across mapping-like objects."""
    target = name.lower()
    try:
        for key, value in headers.items():
            if str(key).lower() == target:
                return str(value) if value is not None else None
    except AttributeError:
        return None
    return None


def verify_webhook_signature(
    provider: str,
    payload_bytes: bytes,
    headers,
    secret: str | None,
) -> bool:
    """Verify a provider webhook signature over the raw request body.

    Generic HMAC-SHA256 hex digest compared against the
    ``X-Voice-Signature`` header (``X-Twilio-Signature`` is also
    accepted for Twilio providers).  Timing-safe comparison.

    Fail-closed: a missing configured secret or a missing/invalid
    signature rejects the event.  Only the ``mock`` provider is
    exempt (local development and tests — never a real transport).
    """
    if provider == "mock":
        return True
    if not secret:
        return False

    provided: str | None = None
    for header in _SIGNATURE_HEADERS:
        value = _header_value(headers, header)
        if value:
            provided = value.strip()
            break
    if not provided:
        return False

    expected = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return hmac.compare_digest(expected.hexdigest(), provided.lower())


def compose_voice_event_id(provider_reference: str, event_type: str) -> str:
    """Build the idempotent external event id for a voice callback.

    Providers (e.g. Twilio) reuse the same CallSid for every status
    callback of a call.  The composite ``{CallSid}:{CallStatus}`` is
    the smallest id that makes replay idempotency meaningful: the
    same status repeated is a duplicate; distinct statuses are
    distinct events.
    """
    return f"{provider_reference}:{event_type.strip().lower()}"


class VoiceWebhookService:
    """Idempotent provider-event ingestion for voice calls."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        orchestration: VoiceProviderOrchestrationService,
    ) -> None:
        self.session = session
        self.orchestration = orchestration
        self.webhook_repo = WebhookRepository(session)
        self.audit_repo = AuditRepository(session)

    async def process_event(
        self,
        *,
        provider: str,
        external_event_id: str,
        event_type: str,
        payload: dict | None = None,
        call: VoiceCall | None = None,
    ) -> dict:
        """Persist and process a provider voice callback.

        Returns ``{"status": "duplicate"}`` for replays (no state
        change) or ``{"status": "accepted", ...}`` after processing.
        Processing failures mark the webhook row FAILED with error
        metadata and re-raise — the transport layer decides the HTTP
        response.
        """
        existing = await self.webhook_repo.get_by_provider_event(provider, external_event_id)
        if existing is not None:
            logger.info(
                "voice_webhook_duplicate",
                provider=provider,
                external_event_id=external_event_id,
            )
            return {"status": "duplicate", "webhook_id": str(existing.id)}

        webhook = CommunicationWebhook(
            provider=provider,
            external_event_id=external_event_id,
            event_type=event_type,
            raw_payload=payload,
            received_at=_utcnow(),
        )
        webhook = await self.webhook_repo.create(webhook)

        try:
            resolved = call or await self._resolve_call_by_reference(external_event_id)

            if resolved is not None:
                await self._apply_event(
                    webhook,
                    resolved,
                    provider=provider,
                    external_event_id=external_event_id,
                    event_type=event_type,
                    payload=payload,
                )

            webhook.processing_status = "PROCESSED"
            webhook.processed_at = _utcnow()
            await self.webhook_repo.update(webhook)
            return {
                "status": "accepted",
                "webhook_id": str(webhook.id),
                "call_id": str(resolved.id) if resolved is not None else None,
            }
        except Exception as exc:
            webhook.processing_status = "FAILED"
            webhook.error_metadata = {
                "error": str(exc),
                "event_type": event_type,
            }
            await self.webhook_repo.update(webhook)
            raise

    # ── Internal helpers ──

    async def _apply_event(
        self,
        webhook: CommunicationWebhook,
        call: VoiceCall,
        *,
        provider: str,
        external_event_id: str,
        event_type: str,
        payload: dict | None,
    ) -> None:
        """Apply one resolved provider event to a call.

        - Mapped statuses: transition through the deterministic
          orchestration layer, then audit the significant change.
        - No-op acknowledgments ("queued"): note on the attempt only.
        - Anything else: rejected by the mapping (fail-closed).
        """
        normalized = event_type.strip().lower()
        status_before = call.status

        if normalized in PROVIDER_NOOP_STATUSES:
            await self._note_noop_on_attempt(call, normalized)
        elif normalized in PROVIDER_STATUS_TRANSITIONS:
            await self.orchestration.sync_provider_status(call, event_type, payload=payload)
        else:
            raise DomainError(f"Unknown provider call status: '{event_type}'")

        webhook.voice_call_id = call.id

        # Audit only significant events — an actual call-state change.
        if call.status != status_before:
            await self._audit_sync(
                call,
                provider=provider,
                external_event_id=external_event_id,
                event_type=normalized,
                previous_status=status_before,
            )

    async def _note_noop_on_attempt(self, call: VoiceCall, normalized: str) -> None:
        """Record a provider acknowledgment on the latest attempt."""
        attempts = await self.orchestration.attempt_repo.list_for_call(call.id)
        if not attempts:
            return
        attempt = attempts[-1]
        attempt.status = normalized.upper()
        await self.orchestration.attempt_repo.update(attempt)

    async def resolve_call(self, provider_reference: str) -> VoiceCall | None:
        """Resolve a call by provider reference (system-authority).

        Public seam for webhook endpoints: the call must be resolved
        before its business's webhook signature secret can be loaded.
        """
        return await self._resolve_call_by_reference(provider_reference)

    async def _resolve_call_by_reference(self, external_event_id: str) -> VoiceCall | None:
        """Resolve a call from a provider reference (CallSid).

        The composite event id ``{CallSid}:{CallStatus}`` resolves via
        its CallSid portion.  Lookup covers the call-level reference
        and attempt-level references (redialed calls hold a fresh SID
        per dial).  Deliberately not business-scoped: provider
        callbacks are system-authority; business scope is preserved
        on the resolved call row itself.
        """
        candidates = [external_event_id]
        if ":" in external_event_id:
            candidates.append(external_event_id.split(":", 1)[0])

        for reference in candidates:
            result = await self.session.execute(
                select(VoiceCall).where(
                    VoiceCall.provider_reference == reference,
                    VoiceCall.deleted_at.is_(None),
                )
            )
            call = result.scalars().first()
            if call is not None:
                return call

            result = await self.session.execute(
                select(VoiceCall)
                .join(VoiceCallAttempt, VoiceCallAttempt.call_id == VoiceCall.id)
                .where(
                    VoiceCallAttempt.provider_reference == reference,
                    VoiceCall.deleted_at.is_(None),
                )
                .limit(1)
            )
            call = result.scalars().first()
            if call is not None:
                return call

        return None

    async def _audit_sync(
        self,
        call: VoiceCall,
        *,
        provider: str,
        external_event_id: str,
        event_type: str,
        previous_status: str,
    ) -> None:
        """Record provider-event provenance for a state change."""
        evidence: dict = {
            "call_id": str(call.id),
            "call_type": call.call_type,
            "purpose": call.purpose,
            "provider": provider,
            "provider_event_id": external_event_id,
            "event_type": event_type,
            "mapped_status": call.status,
            "previous_status": previous_status,
        }
        event = CommunicationAuditEvent(
            event_type=AuditEventType.CALL_PROVIDER_STATE_SYNC.value,
            actor_id=None,
            business_id=call.business_id,
            customer_id=call.customer_id,
            channel=_AUDIT_CHANNEL,
            purpose=call.purpose,
            communication_id=call.communication_id,
            brain_version_id=call.brain_version_id,
            decision_evidence=evidence,
            metadata_=evidence,
        )
        await self.audit_repo.create(event)
