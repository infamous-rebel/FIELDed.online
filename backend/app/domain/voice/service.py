"""Voice call lifecycle service.

Deterministic, authoritative lifecycle management for voice calls,
call sessions, and human escalations.

Every state transition is validated against the explicit transition
maps in ``app.domain.common.enums`` and produces audit evidence via
the existing Phase 14A communication audit model.  Invalid transitions
fail explicitly.  The AI agent never mutates call state directly.

This service performs persistence only — it never calls an external
voice provider.  Provider execution belongs to the orchestration
layer in a later 14B block, on top of the unchanged Phase 14A
``VoiceProvider`` contract.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.enums import (
    CALL_PURPOSE_TYPE,
    CALL_SESSION_TRANSITIONS,
    CALL_TRANSITIONS,
    ESCALATION_TRANSITIONS,
    AuditEventType,
    CallParticipantType,
    CallPurpose,
    CallSessionStatus,
    CallStatus,
    CallType,
    EscalationStatus,
)
from app.domain.communication.repository import AuditRepository
from app.domain.voice.models import (
    VoiceCall,
    VoiceCallAttempt,
    VoiceCallEscalation,
    VoiceCallParticipant,
    VoiceCallSession,
)
from app.domain.voice.outbox_integration import emit_voice_event
from app.domain.voice.repository import (
    CallAgentConfigRepository,
    VoiceCallAttemptRepository,
    VoiceCallEscalationRepository,
    VoiceCallParticipantRepository,
    VoiceCallRepository,
    VoiceCallSessionRepository,
)
from app.exceptions import ConflictError, DomainError, StateTransitionError

logger = logging.getLogger(__name__)

_AUDIT_CHANNEL = "VOICE"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class VoiceCallLifecycleService:
    """Deterministic lifecycle management for voice calls.

    Validates every transition against the call state machine,
    maintains lifecycle timestamps, ends conversational sessions when
    a call terminates, and records an audit event for every
    significant transition.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.call_repo = VoiceCallRepository(session)
        self.participant_repo = VoiceCallParticipantRepository(session)
        self.attempt_repo = VoiceCallAttemptRepository(session)
        self.session_repo = VoiceCallSessionRepository(session)
        self.escalation_repo = VoiceCallEscalationRepository(session)
        self.config_repo = CallAgentConfigRepository(session)
        self.audit_repo = AuditRepository(session)

    # ── Request / authorization ──

    async def request_call(
        self,
        *,
        business_id: uuid.UUID,
        to_number: str,
        purpose: str,
        provider: str,
        idempotency_key: str,
        call_type: str | None = None,
        from_number: str | None = None,
        customer_id: uuid.UUID | None = None,
        enquiry_id: uuid.UUID | None = None,
        quote_id: uuid.UUID | None = None,
        booking_id: uuid.UUID | None = None,
        service_execution_id: uuid.UUID | None = None,
        invoice_id: uuid.UUID | None = None,
        communication_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
        brain_version_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        source: str | None = None,
    ) -> VoiceCall:
        """Request a new call.

        Validation order (deterministic, fail-closed):
        1. Purpose must map to a declared call type — a marketing
           purpose can never masquerade as a transactional call (and
           vice versa), regardless of the recipient's customer status.
        2. Call Agent operational configuration must exist, be enabled,
           and explicitly enable the requested calling class.
        3. Idempotency — a repeated request with the same
           (business, idempotency_key) returns the existing call
           instead of creating a duplicate.
        """
        try:
            purpose_enum = CallPurpose(purpose)
        except ValueError as exc:
            raise DomainError(f"Unknown call purpose: '{purpose}'") from exc

        derived_type = CALL_PURPOSE_TYPE[purpose_enum]
        if call_type is not None and call_type != derived_type.value:
            raise DomainError(
                f"Call purpose '{purpose}' is a {derived_type.value} purpose "
                f"and cannot be used with call type '{call_type}'"
            )

        config = await self.config_repo.get_for_business(business_id)
        if config is None:
            raise DomainError("Call Agent is not configured for this business")
        if not config.enabled:
            raise DomainError("Call Agent is disabled for this business")
        if derived_type == CallType.TRANSACTIONAL:
            if not config.transactional_calling_enabled:
                raise DomainError("Transactional calling is disabled for this business")
        else:
            if not config.marketing_calling_enabled:
                raise DomainError("Marketing calling is disabled for this business")

        existing = await self.call_repo.get_by_idempotency_key(business_id, idempotency_key)
        if existing is not None:
            return existing

        resolved_from = from_number or config.default_from_number
        call = VoiceCall(
            business_id=business_id,
            customer_id=customer_id,
            enquiry_id=enquiry_id,
            quote_id=quote_id,
            booking_id=booking_id,
            service_execution_id=service_execution_id,
            invoice_id=invoice_id,
            communication_id=communication_id,
            campaign_id=campaign_id,
            call_type=derived_type.value,
            purpose=purpose_enum.value,
            status=CallStatus.REQUESTED.value,
            to_number=to_number,
            from_number=resolved_from,
            provider=provider,
            brain_version_id=brain_version_id,
            idempotency_key=idempotency_key,
            requested_at=_utcnow(),
        )
        call = await self.call_repo.create(call)

        await self._audit(
            call,
            AuditEventType.CALL_REQUESTED,
            previous_status=None,
            new_status=call.status,
            actor_id=actor_id,
            reason=source,
            brain_version_id=brain_version_id,
        )

        logger.info(
            "voice_call_requested",
            call_id=str(call.id),
            business_id=str(business_id),
            call_type=call.call_type,
            purpose=call.purpose,
        )
        return call

    async def authorize_call(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
        brain_version_id: uuid.UUID | None = None,
    ) -> VoiceCall:
        """Authorize a requested call (governed by the Business Brain)."""
        call = await self._transition_call(
            call,
            CallStatus.AUTHORIZED,
            event_type=AuditEventType.CALL_AUTHORIZED,
            actor_id=actor_id,
            reason=reason,
            brain_version_id=brain_version_id,
        )
        call.authorized_at = _utcnow()
        if brain_version_id is not None:
            call.brain_version_id = brain_version_id
        return await self.call_repo.update(call)

    # ── Dialing lifecycle ──

    async def queue_call(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Queue an authorized call for provider initiation."""
        call = await self._transition_call(
            call,
            CallStatus.QUEUED,
            event_type=AuditEventType.CALL_QUEUED,
            actor_id=actor_id,
            reason=reason,
        )
        call.queued_at = _utcnow()
        return await self.call_repo.update(call)

    async def mark_initiating(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Mark the call as being initiated with the provider."""
        call = await self._transition_call(
            call,
            CallStatus.INITIATING,
            event_type=AuditEventType.CALL_INITIATED,
            actor_id=actor_id,
            reason=reason,
        )
        call.initiated_at = _utcnow()
        return await self.call_repo.update(call)

    async def mark_ringing(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Mark the call as ringing at the recipient."""
        return await self._transition_call(
            call,
            CallStatus.RINGING,
            event_type=AuditEventType.CALL_RINGING,
            actor_id=actor_id,
            reason=reason,
        )

    async def mark_connected(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Mark the call as connected (recipient answered)."""
        call = await self._transition_call(
            call,
            CallStatus.CONNECTED,
            event_type=AuditEventType.CALL_CONNECTED,
            actor_id=actor_id,
            reason=reason,
        )
        call.connected_at = _utcnow()
        return await self.call_repo.update(call)

    # ── Session ──

    async def start_session(
        self,
        call: VoiceCall,
        *,
        language: str | None = None,
        agent_session_reference: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallSession:
        """Start the conversational session for a connected call.

        Bridges CONNECTED -> IN_PROGRESS.  Only one active session is
        permitted per call.
        """
        if CallStatus(call.status) != CallStatus.CONNECTED:
            raise StateTransitionError(
                f"Cannot start a session for a call in status "
                f"'{call.status}'. Call must be CONNECTED."
            )

        existing = await self.session_repo.get_active_for_call(call.id)
        if existing is not None:
            raise ConflictError("An active session already exists for this call")

        session_row = VoiceCallSession(
            call_id=call.id,
            session_status=CallSessionStatus.ACTIVE.value,
            started_at=_utcnow(),
            agent_session_reference=agent_session_reference,
            language=language,
        )
        session_row = await self.session_repo.create(session_row)

        await self._transition_call(
            call,
            CallStatus.IN_PROGRESS,
            event_type=AuditEventType.CALL_IN_PROGRESS,
            actor_id=actor_id,
        )
        await self._audit(
            call,
            AuditEventType.CALL_SESSION_STARTED,
            previous_status=call.status,
            new_status=call.status,
            actor_id=actor_id,
        )

        logger.info("voice_call_session_started", call_id=str(call.id))
        return session_row

    # ── Terminal transitions ──

    async def complete_call(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Complete the call and end any active session."""
        call = await self._transition_call(
            call,
            CallStatus.COMPLETED,
            event_type=AuditEventType.CALL_COMPLETED,
            actor_id=actor_id,
            reason=reason,
        )
        call.completed_at = _utcnow()
        await self._end_active_session(call, CallSessionStatus.COMPLETED, actor_id=actor_id)
        call = await self.call_repo.update(call)
        await emit_voice_event(
            self.session,
            business_id=call.business_id,
            event_type="voice.call_completed",
            aggregate_type="voice_call",
            aggregate_id=call.id,
            payload={
                "call_id": str(call.id),
                "purpose": call.purpose,
                "customer_id": (
                    str(call.customer_id) if call.customer_id else None
                ),
            },
        )
        return call

    async def fail_call(
        self,
        call: VoiceCall,
        *,
        failure_code: str | None = None,
        failure_reason: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCall:
        """Fail the call and end any active session."""
        call = await self._transition_call(
            call,
            CallStatus.FAILED,
            event_type=AuditEventType.CALL_FAILED,
            actor_id=actor_id,
            reason=failure_reason,
        )
        call.failed_at = _utcnow()
        call.failure_code = failure_code
        call.failure_reason = failure_reason
        await self._end_active_session(call, CallSessionStatus.FAILED, actor_id=actor_id)
        call = await self.call_repo.update(call)
        await emit_voice_event(
            self.session,
            business_id=call.business_id,
            event_type="voice.call_failed",
            aggregate_type="voice_call",
            aggregate_id=call.id,
            payload={
                "call_id": str(call.id),
                "purpose": call.purpose,
                "failure_code": call.failure_code,
                "failure_reason": call.failure_reason,
                "customer_id": (
                    str(call.customer_id) if call.customer_id else None
                ),
            },
        )
        return call

    async def mark_no_answer(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Mark the call as not answered (terminal)."""
        return await self._transition_call(
            call,
            CallStatus.NO_ANSWER,
            event_type=AuditEventType.CALL_NO_ANSWER,
            actor_id=actor_id,
            reason=reason,
        )

    async def mark_busy(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Mark the call as busy (terminal)."""
        return await self._transition_call(
            call,
            CallStatus.BUSY,
            event_type=AuditEventType.CALL_BUSY,
            actor_id=actor_id,
            reason=reason,
        )

    async def mark_declined(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Mark the call as declined by the recipient (terminal)."""
        return await self._transition_call(
            call,
            CallStatus.DECLINED,
            event_type=AuditEventType.CALL_DECLINED,
            actor_id=actor_id,
            reason=reason,
        )

    async def cancel_call(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Cancel the call (pre-connect states only)."""
        return await self._transition_call(
            call,
            CallStatus.CANCELLED,
            event_type=AuditEventType.CALL_CANCELLED,
            actor_id=actor_id,
            reason=reason,
        )

    async def expire_call(
        self,
        call: VoiceCall,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCall:
        """Expire the call (unactioned request/queue states)."""
        return await self._transition_call(
            call,
            CallStatus.EXPIRED,
            event_type=AuditEventType.CALL_EXPIRED,
            actor_id=actor_id,
            reason=reason,
        )

    async def escalate_call(
        self,
        call: VoiceCall,
        *,
        escalation_reason: str,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallEscalation:
        """Escalate the call to a human.

        Marks the call ESCALATED (terminal for the AI-handled call),
        ends the conversational session, and persists explicit
        escalation state starting at REQUESTED.  The actual handoff
        behavior belongs to a later 14B block.
        """
        self._validate_transition(call, CallStatus.ESCALATED)

        escalation = VoiceCallEscalation(
            call_id=call.id,
            escalation_status=EscalationStatus.REQUESTED.value,
            escalation_reason=escalation_reason,
            requested_at=_utcnow(),
        )
        escalation = await self.escalation_repo.create(escalation)

        # Mark the conversational session as escalated before ending it
        active_session = await self.session_repo.get_active_for_call(call.id)
        if active_session is not None:
            active_session.human_escalation_requested = True
            active_session.human_escalation_at = _utcnow()
            await self.session_repo.update(active_session)

        await self._end_active_session(call, CallSessionStatus.ESCALATED, actor_id=actor_id)

        await self._transition_call(
            call,
            CallStatus.ESCALATED,
            event_type=AuditEventType.CALL_ESCALATED,
            actor_id=actor_id,
            reason=escalation_reason,
        )

        logger.info(
            "voice_call_escalated",
            call_id=str(call.id),
            escalation_id=str(escalation.id),
        )
        await emit_voice_event(
            self.session,
            business_id=call.business_id,
            event_type="voice.escalation_requested",
            aggregate_type="voice_call_escalation",
            aggregate_id=escalation.id,
            payload={
                "call_id": str(call.id),
                "escalation_id": str(escalation.id),
                "escalation_reason": escalation.escalation_reason,
                "customer_id": (
                    str(call.customer_id) if call.customer_id else None
                ),
            },
        )
        return escalation

    # ── Participants / attempts ──

    async def add_participant(
        self,
        call: VoiceCall,
        *,
        participant_type: str,
        phone_number: str,
        user_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        business_member_id: uuid.UUID | None = None,
        display_name: str | None = None,
        role: str | None = None,
    ) -> VoiceCallParticipant:
        """Add a participant to a call."""
        CallParticipantType(participant_type)  # fail fast on unknown types
        participant = VoiceCallParticipant(
            call_id=call.id,
            participant_type=participant_type,
            user_id=user_id,
            customer_id=customer_id,
            business_member_id=business_member_id,
            phone_number=phone_number,
            display_name=display_name,
            role=role,
        )
        return await self.participant_repo.create(participant)

    async def record_attempt(
        self,
        call: VoiceCall,
        *,
        provider: str,
        status: str = "REQUESTED",
        provider_reference: str | None = None,
        failure_code: str | None = None,
        failure_reason: str | None = None,
        retryable: bool = False,
        provider_payload_reference: str | None = None,
    ) -> VoiceCallAttempt:
        """Append a provider attempt to a call (append-oriented)."""
        attempt_number = await self.attempt_repo.next_attempt_number(call.id)
        attempt = VoiceCallAttempt(
            call_id=call.id,
            attempt_number=attempt_number,
            provider=provider,
            provider_reference=provider_reference,
            status=status,
            requested_at=_utcnow(),
            failure_code=failure_code,
            failure_reason=failure_reason,
            retryable=retryable,
            provider_payload_reference=provider_payload_reference,
        )
        return await self.attempt_repo.create(attempt)

    # ── Escalation lifecycle ──

    async def assign_escalation(
        self,
        escalation: VoiceCallEscalation,
        *,
        assigned_member_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallEscalation:
        """Assign a requested escalation to a business member."""
        await self._transition_escalation(
            escalation,
            EscalationStatus.ASSIGNED,
            event_type=AuditEventType.CALL_ESCALATION_ASSIGNED,
            actor_id=actor_id,
        )
        escalation.assigned_member_id = assigned_member_id
        return await self.escalation_repo.update(escalation)

    async def accept_escalation(
        self,
        escalation: VoiceCallEscalation,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallEscalation:
        """Human accepts the escalation (handoff point)."""
        await self._transition_escalation(
            escalation,
            EscalationStatus.ACCEPTED,
            event_type=AuditEventType.CALL_ESCALATION_ACCEPTED,
            actor_id=actor_id,
        )
        escalation.accepted_at = _utcnow()
        return await self.escalation_repo.update(escalation)

    async def resolve_escalation(
        self,
        escalation: VoiceCallEscalation,
        *,
        resolution_notes: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallEscalation:
        """Resolve an accepted escalation."""
        await self._transition_escalation(
            escalation,
            EscalationStatus.RESOLVED,
            event_type=AuditEventType.CALL_ESCALATION_RESOLVED,
            actor_id=actor_id,
        )
        escalation.resolved_at = _utcnow()
        escalation.resolution_notes = resolution_notes
        return await self.escalation_repo.update(escalation)

    async def cancel_escalation(
        self,
        escalation: VoiceCallEscalation,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> VoiceCallEscalation:
        """Cancel a requested/assigned escalation."""
        await self._transition_escalation(
            escalation,
            EscalationStatus.CANCELLED,
            event_type=AuditEventType.CALL_ESCALATION_CANCELLED,
            actor_id=actor_id,
            reason=reason,
        )
        return await self.escalation_repo.update(escalation)

    # ── Internal helpers ──

    @staticmethod
    def _validate_transition(call: VoiceCall, target: CallStatus) -> None:
        current = CallStatus(call.status)
        allowed = CALL_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise StateTransitionError(
                f"Cannot transition call from '{current.value}' to "
                f"'{target.value}'. Allowed: "
                f"{[s.value for s in allowed] or 'none (terminal state)'}"
            )

    async def _transition_call(
        self,
        call: VoiceCall,
        target: CallStatus,
        *,
        event_type: AuditEventType,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
        brain_version_id: uuid.UUID | None = None,
    ) -> VoiceCall:
        """Validate a transition, apply it, and record audit evidence."""
        previous_status = call.status
        self._validate_transition(call, target)

        call.status = target.value
        call = await self.call_repo.update(call)

        await self._audit(
            call,
            event_type,
            previous_status=previous_status,
            new_status=call.status,
            actor_id=actor_id,
            reason=reason,
            brain_version_id=brain_version_id,
        )

        logger.info(
            "voice_call_transition",
            call_id=str(call.id),
            from_status=previous_status,
            to_status=call.status,
        )
        return call

    async def _end_active_session(
        self,
        call: VoiceCall,
        target: CallSessionStatus,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallSession | None:
        """End the active session of a terminating call, if any."""
        session_row = await self.session_repo.get_active_for_call(call.id)
        if session_row is None:
            return None

        current = CallSessionStatus(session_row.session_status)
        allowed = CALL_SESSION_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise StateTransitionError(
                f"Cannot transition call session from '{current.value}' to "
                f"'{target.value}'. Allowed: "
                f"{[s.value for s in allowed] or 'none (terminal state)'}"
            )

        session_row.session_status = target.value
        session_row.ended_at = _utcnow()
        session_row = await self.session_repo.update(session_row)

        logger.info(
            "voice_call_session_ended",
            call_id=str(call.id),
            session_id=str(session_row.id),
            to_status=session_row.session_status,
        )
        return session_row

    async def _transition_escalation(
        self,
        escalation: VoiceCallEscalation,
        target: EscalationStatus,
        *,
        event_type: AuditEventType,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> None:
        """Validate an escalation transition, apply it, record audit."""
        current = EscalationStatus(escalation.escalation_status)
        allowed = ESCALATION_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise StateTransitionError(
                f"Cannot transition escalation from '{current.value}' to "
                f"'{target.value}'. Allowed: "
                f"{[s.value for s in allowed] or 'none (terminal state)'}"
            )

        previous_status = escalation.escalation_status
        escalation.escalation_status = target.value
        await self.escalation_repo.update(escalation)

        # Escalation audit evidence rides on the parent call
        call = await self.call_repo.get_by_id(
            escalation.call_id,
            business_id=await self._call_business_id(escalation.call_id),
        )
        if call is not None:
            await self._audit(
                call,
                event_type,
                previous_status=previous_status,
                new_status=escalation.escalation_status,
                actor_id=actor_id,
                reason=reason,
            )

    async def _call_business_id(self, call_id: uuid.UUID) -> uuid.UUID:
        """Resolve the business id for a call id (escalation audit path)."""
        from sqlalchemy import select

        result = await self.session.execute(
            select(VoiceCall.business_id).where(VoiceCall.id == call_id)
        )
        business_id = result.scalar_one_or_none()
        if business_id is None:
            raise ConflictError("Escalation references a missing call")
        return business_id

    async def _audit(
        self,
        call: VoiceCall,
        event_type: AuditEventType,
        *,
        previous_status: str | None,
        new_status: str | None,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
        brain_version_id: uuid.UUID | None = None,
    ) -> None:
        """Record call provenance in the Phase 14A audit model.

        Preserves: business_id, call_id, call_type, purpose,
        previous_status, new_status, brain_version_id, actor/source,
        timestamp, and reason.  Historical call state is never
        rewritten to erase previous decisions.
        """
        from app.domain.communication.models import CommunicationAuditEvent

        evidence: dict = {
            "call_id": str(call.id),
            "call_type": call.call_type,
            "purpose": call.purpose,
            "previous_status": previous_status,
            "new_status": new_status,
        }
        if reason is not None:
            evidence["reason"] = reason
        if actor_id is not None:
            evidence["actor_id"] = str(actor_id)

        event = CommunicationAuditEvent(
            event_type=event_type.value,
            actor_id=actor_id,
            business_id=call.business_id,
            customer_id=call.customer_id,
            channel=_AUDIT_CHANNEL,
            purpose=call.purpose,
            communication_id=call.communication_id,
            brain_version_id=brain_version_id or call.brain_version_id,
            decision_evidence=evidence,
            metadata_=evidence,
        )
        await self.audit_repo.create(event)
