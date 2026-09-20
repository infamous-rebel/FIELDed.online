"""Voice provider orchestration service.

The ONLY layer that dials.  Bridges the deterministic call lifecycle
(``VoiceCallLifecycleService``) to the unchanged Phase 14A
``VoiceProvider`` adapter contract:

- Provider outcomes never confer authority.  A successful dial leaves
  the call INITIATING; progression to RINGING and beyond arrives only
  through provider state sync (webhook-driven).
- Every dial appends exactly one ``VoiceCallAttempt``; retries keep
  the call INITIATING instead of inventing new lifecycle states.
- Idempotent initiation: a call holding a live provider reference is
  never dialed twice.
- Attempt limits and retry intervals come from the business Call
  Agent configuration — never from AI output or provider payloads.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.domain.common.enums import CALL_TRANSITIONS, AuditEventType, CallStatus
from app.domain.communication.models import CommunicationAuditEvent
from app.domain.communication.repository import AuditRepository
from app.domain.voice.models import VoiceCall
from app.domain.voice.outbox_integration import emit_voice_event
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import DomainError, StateTransitionError

logger = logging.getLogger(__name__)

_AUDIT_CHANNEL = "VOICE"

# Deterministic provider-status -> call-status mapping.  Keys are the
# lowercased status strings used by provider callbacks; values are
# CallStatus values.  Unknown provider statuses are rejected
# (fail-closed) rather than guessed.
PROVIDER_STATUS_TRANSITIONS: dict[str, str] = {
    "ringing": CallStatus.RINGING.value,
    "in-progress": CallStatus.CONNECTED.value,
    "completed": CallStatus.COMPLETED.value,
    "busy": CallStatus.BUSY.value,
    "no-answer": CallStatus.NO_ANSWER.value,
    "failed": CallStatus.FAILED.value,
    "canceled": CallStatus.CANCELLED.value,
    "declined": CallStatus.DECLINED.value,
}

# Provider lifecycle acknowledgments that carry no call-state
# transition (e.g. Twilio "queued").  Webhook processing persists
# them for provenance and notes them on the attempt record, but the
# call state machine is untouched.
PROVIDER_NOOP_STATUSES: frozenset[str] = frozenset(
    {
        "queued",
        "accepted",
        "initiated",
        "scheduled",
    }
)

# States from which a (re)dial may be attempted.
_INITIABLE_STATUSES: frozenset[CallStatus] = frozenset(
    {
        CallStatus.AUTHORIZED,
        CallStatus.QUEUED,
        CallStatus.INITIATING,
    }
)

# Provider-reported outcomes meaning "the recipient side failed to
# connect".  Unreachable directly from INITIATING in the call state
# machine, so they are modeled deterministically as a failed
# initiation.
_PROVIDER_CONNECTION_FAILURES: frozenset[CallStatus] = frozenset(
    {
        CallStatus.BUSY,
        CallStatus.NO_ANSWER,
        CallStatus.DECLINED,
    }
)

# States with no outgoing transitions — derived from the transition
# map itself so this set can never drift from the state machine.
_TERMINAL_CALL_STATUSES: frozenset[CallStatus] = frozenset(
    status for status, targets in CALL_TRANSITIONS.items() if not targets
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class VoiceProviderOrchestrationService:
    """Drives the call lifecycle through a voice provider adapter."""

    def __init__(
        self,
        session: AsyncSession,
        voice_provider: VoiceProvider,
        lifecycle: VoiceCallLifecycleService | None = None,
    ) -> None:
        self.session = session
        self.voice_provider = voice_provider
        self.lifecycle = lifecycle or VoiceCallLifecycleService(session)
        self.call_repo = self.lifecycle.call_repo
        self.attempt_repo = self.lifecycle.attempt_repo
        self.config_repo = self.lifecycle.config_repo
        self.audit_repo = AuditRepository(session)

    # ── Initiation ──

    async def initiate_call(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        twiml_url: str | None = None,
    ) -> VoiceCall:
        """Dial a call through the provider adapter.

        Validation order (deterministic, fail-closed):
        1. The call must be in a dialable state (AUTHORIZED, QUEUED,
           or INITIATING — the retry-stable state).
        2. Idempotency — a call already holding a live provider
           reference is returned unchanged (never dialed twice).
        3. Attempt/frequency guards from the Call Agent
           configuration: attempts exhausted fails the call;
           retrying before the configured interval is rejected.

        ``twiml_url`` is the public URL Twilio should request for
        call instructions (Phase 14C).  When provided, it is set as
        the callback_url on the VoiceCallRequest so the Twilio adapter
        passes it as the ``Url`` parameter.
        """
        if CallStatus(call.status) not in _INITIABLE_STATUSES:
            raise StateTransitionError(
                f"Cannot initiate a call in status '{call.status}'. "
                f"Dialable statuses: "
                f"{[s.value for s in sorted(_INITIABLE_STATUSES, key=lambda v: v.value)]}"
            )

        attempts = await self.attempt_repo.list_for_call(call.id)

        # Idempotency — a live provider reference means this call is
        # already (or has been) dialed.  Never dial twice.
        if call.provider_reference is not None:
            live = any(
                attempt.provider_reference == call.provider_reference
                and attempt.status != CallStatus.FAILED.value
                for attempt in attempts
            )
            if live:
                return call

        config = await self.config_repo.get_for_business(call.business_id)
        if config is None:
            raise DomainError("Call Agent is not configured for this business")

        if len(attempts) >= config.max_attempts:
            return await self.lifecycle.fail_call(
                call,
                failure_code="MAX_ATTEMPTS_EXCEEDED",
                failure_reason=(f"Provider attempt limit of {config.max_attempts} reached"),
                actor_id=actor_id,
            )

        last_attempt = attempts[-1] if attempts else None
        if (
            last_attempt is not None
            and last_attempt.status == CallStatus.FAILED.value
            and last_attempt.retryable
        ):
            elapsed = (_utcnow() - last_attempt.requested_at).total_seconds()
            if elapsed < config.retry_interval_seconds:
                raise DomainError(
                    f"Provider retry interval of {config.retry_interval_seconds}s "
                    f"not elapsed since the last dial attempt "
                    f"({int(elapsed)}s elapsed)"
                )

        if not call.from_number:
            raise DomainError("Call has no from_number configured for dialing")

        if CallStatus(call.status) == CallStatus.AUTHORIZED:
            call = await self.lifecycle.queue_call(
                call, actor_id=actor_id, reason="provider orchestration dial"
            )
        if CallStatus(call.status) == CallStatus.QUEUED:
            call = await self.lifecycle.mark_initiating(
                call, actor_id=actor_id, reason="provider orchestration dial"
            )

        attempt = await self.lifecycle.record_attempt(
            call,
            provider=self.voice_provider.provider_name,
            status="REQUESTED",
        )

        request = VoiceCallRequest(
            to=call.to_number,
            from_number=call.from_number,
            callback_url=twiml_url,
            metadata={
                "call_id": str(call.id),
                "business_id": str(call.business_id),
                "purpose": call.purpose,
            },
        )
        result = await self.voice_provider.initiate_call(request)

        if result.success:
            attempt.status = "DIALED"
            attempt.provider_reference = result.provider_reference
            attempt.started_at = _utcnow()
            await self.attempt_repo.update(attempt)

            call.provider_reference = result.provider_reference
            call = await self.call_repo.update(call)

            await self._audit_initiation_outcome(call, result=result, actor_id=actor_id)
            logger.info(
                "voice_call_dialed",
                call_id=str(call.id),
                provider=self.voice_provider.provider_name,
                provider_reference=result.provider_reference,
            )
            await emit_voice_event(
                self.session,
                business_id=call.business_id,
                event_type="voice.call_initiated",
                aggregate_type="voice_call",
                aggregate_id=call.id,
                slot=str(attempt.id),
                payload={
                    "call_id": str(call.id),
                    "to_number": call.to_number,
                    "purpose": call.purpose,
                    "provider": self.voice_provider.provider_name,
                    "provider_reference": result.provider_reference,
                    "customer_id": (str(call.customer_id) if call.customer_id else None),
                    "campaign_id": (str(call.campaign_id) if call.campaign_id else None),
                },
            )
            return call

        attempt.status = CallStatus.FAILED.value
        attempt.retryable = result.retryable
        attempt.failure_code = "PROVIDER_ERROR"
        attempt.failure_reason = result.error
        await self.attempt_repo.update(attempt)

        await self._audit_initiation_outcome(call, result=result, actor_id=actor_id)

        if result.retryable:
            # Call stays INITIATING — the retry-stable state.  A later
            # initiation (after the retry interval) appends attempt #2.
            logger.info(
                "voice_call_dial_retryable_failure",
                call_id=str(call.id),
                error=result.error,
            )
            return call

        return await self.lifecycle.fail_call(
            call,
            failure_code="PROVIDER_ERROR",
            failure_reason=result.error,
            actor_id=actor_id,
        )

    # ── Provider state synchronization ──

    async def sync_provider_status(
        self,
        call: VoiceCall,
        provider_status: str,
        *,
        payload: dict | None = None,
        actor_id: uuid.UUID | None = None,
        failure_reason: str | None = None,
    ) -> VoiceCall:
        """Synchronize a call with a provider-reported status.

        Deterministic mapping via ``PROVIDER_STATUS_TRANSITIONS`` with
        explicit pre-steps for provider sequences the call state
        machine cannot express directly:

        - ``completed`` while RINGING: connect first, then complete
          (the recipient answered and the call ended without the
          conversation runtime observing an ``in-progress`` event).
        - ``busy`` / ``no-answer`` / ``declined`` while INITIATING:
          modeled as a failed initiation (these outcomes are
          unreachable directly from INITIATING).

        Terminal calls are returned unchanged — provider events for
        calls already in a terminal state are no-ops.
        """
        normalized = provider_status.strip().lower()
        mapped_value = PROVIDER_STATUS_TRANSITIONS.get(normalized)
        if mapped_value is None:
            raise DomainError(f"Unknown provider call status: '{provider_status}'")

        target = CallStatus(mapped_value)
        current = CallStatus(call.status)

        if current in _TERMINAL_CALL_STATUSES:
            logger.info(
                "voice_call_provider_sync_noop_terminal",
                call_id=str(call.id),
                provider_status=normalized,
                call_status=current.value,
            )
            return call
        if current is target:
            # Repeated provider event for the same state — no-op.
            return call

        reason = failure_reason or f"provider reported '{normalized}'"

        if target is CallStatus.COMPLETED and current is CallStatus.RINGING:
            call = await self.lifecycle.mark_connected(
                call, actor_id=actor_id, reason="provider state sync"
            )
            call = await self.lifecycle.complete_call(
                call, actor_id=actor_id, reason="provider state sync"
            )
        elif target in _PROVIDER_CONNECTION_FAILURES and current is CallStatus.INITIATING:
            call = await self.lifecycle.fail_call(
                call,
                failure_code=target.value,
                failure_reason=reason,
                actor_id=actor_id,
            )
        elif target is CallStatus.FAILED:
            call = await self.lifecycle.fail_call(
                call,
                failure_code="PROVIDER_FAILED",
                failure_reason=reason,
                actor_id=actor_id,
            )
        elif target is CallStatus.RINGING:
            call = await self.lifecycle.mark_ringing(
                call, actor_id=actor_id, reason="provider state sync"
            )
        elif target is CallStatus.CONNECTED:
            call = await self.lifecycle.mark_connected(
                call, actor_id=actor_id, reason="provider state sync"
            )
        elif target is CallStatus.COMPLETED:
            call = await self.lifecycle.complete_call(
                call, actor_id=actor_id, reason="provider state sync"
            )
        elif target is CallStatus.BUSY:
            call = await self.lifecycle.mark_busy(call, actor_id=actor_id, reason=reason)
        elif target is CallStatus.NO_ANSWER:
            call = await self.lifecycle.mark_no_answer(call, actor_id=actor_id, reason=reason)
        elif target is CallStatus.DECLINED:
            call = await self.lifecycle.mark_declined(call, actor_id=actor_id, reason=reason)
        elif target is CallStatus.CANCELLED:
            call = await self.lifecycle.cancel_call(
                call, actor_id=actor_id, reason="provider state sync"
            )
        else:  # pragma: no cover — PROVIDER_STATUS_TRANSITIONS is total
            raise DomainError(
                f"Provider status '{provider_status}' has no deterministic transition"
            )

        await self._sync_latest_attempt(call, target, reason=reason)
        return call

    # ── Internal helpers ──

    async def _sync_latest_attempt(
        self,
        call: VoiceCall,
        target: CallStatus,
        *,
        reason: str,
    ) -> None:
        """Sync the most recent attempt row with the provider status."""
        attempts = await self.attempt_repo.list_for_call(call.id)
        if not attempts:
            return

        attempt = attempts[-1]
        attempt.status = target.value
        now = _utcnow()
        if target in _PROVIDER_CONNECTION_FAILURES or target is CallStatus.FAILED:
            attempt.failure_code = target.value
            attempt.failure_reason = reason
        elif target is CallStatus.COMPLETED:
            attempt.completed_at = now
            if attempt.connected_at is None:
                attempt.connected_at = now
        elif target is CallStatus.CONNECTED:
            attempt.connected_at = now
        elif target is CallStatus.RINGING and attempt.started_at is None:
            attempt.started_at = now
        await self.attempt_repo.update(attempt)

    async def _audit_initiation_outcome(
        self,
        call: VoiceCall,
        *,
        result: ProviderResult,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Record provider dial provenance for the initiation outcome."""
        evidence: dict = {
            "call_id": str(call.id),
            "call_type": call.call_type,
            "purpose": call.purpose,
            "provider": self.voice_provider.provider_name,
            "stage": "initiation",
            "provider_reference": result.provider_reference,
            "error": result.error,
            "retryable": result.retryable,
        }
        event = CommunicationAuditEvent(
            event_type=AuditEventType.CALL_PROVIDER_STATE_SYNC.value,
            actor_id=actor_id,
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
