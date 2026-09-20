"""Call Agent conversation runtime.

The AI voice conversation layer for connected calls.  Authority
rules are absolute:

- The agent MUST be governed: it only runs against an ACTIVE
  Business Brain version whose ``communication_config`` contains a
  ``voice_agent`` section.  No brain, no agent (closed-world).
- The AI provider only PROPOSES a turn action through a structured
  schema; every proposal is validated and executed through the
  deterministic FIELDed services (lifecycle, escalation).  The AI
  never mutates call state directly.
- Information collection is restricted to governed collectible
  fields; anything else is rejected (fail-closed).
- Outcomes respect transactional/marketing separation: a marketing
  call may never record a transactional-only outcome.
- Every turn is audited; every state-affecting action is audited.

Instructions are built deterministically from the governed
configuration plus bounded call context — the model is told what it
may do; it is never asked what it may do.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AIProvider
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.common.enums import (
    TRANSACTIONAL_ONLY_OUTCOMES,
    AgentAction,
    AuditEventType,
    CallOutcome,
    CallStatus,
    CallType,
)
from app.domain.communication.models import CommunicationAuditEvent
from app.domain.communication.repository import AuditRepository
from app.domain.identity.models import Business, CustomerProfile
from app.domain.voice.models import VoiceCall, VoiceCallSession
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import DomainError, StateTransitionError

logger = logging.getLogger(__name__)

_AUDIT_CHANNEL = "VOICE"

# Default turn budget when the Brain does not govern one.
_DEFAULT_MAX_TURNS = 20

# Structured proposal contract for a single conversation turn.
AGENT_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "action": {
            "type": "string",
            "enum": [action.value for action in AgentAction],
        },
        "collected_information": {"type": "object"},
        "outcome": {
            "type": ["string", "null"],
            "enum": [outcome.value for outcome in CallOutcome] + [None],
        },
        "outcome_summary": {"type": ["string", "null"]},
        "escalation_reason": {"type": ["string", "null"]},
    },
    "required": ["reply", "action"],
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class VoiceCallAgent:
    """Governed AI conversation runtime for connected voice calls."""

    def __init__(self, session: AsyncSession, ai_provider: AIProvider) -> None:
        self.session = session
        self.ai_provider = ai_provider
        self.lifecycle = VoiceCallLifecycleService(session)
        self.config_repo = self.lifecycle.config_repo
        self.audit_repo = AuditRepository(session)

    # ── Session lifecycle ──

    async def begin(
        self,
        call: VoiceCall,
        *,
        language: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallSession:
        """Start a governed agent session on a CONNECTED call.

        Loads the active BrainVersion, requires the governed
        ``voice_agent`` section, re-checks calling-class enablement,
        records the governing brain version on the call, and seeds
        the conversation log with the deterministic instructions.
        """
        if CallStatus(call.status) != CallStatus.CONNECTED:
            raise StateTransitionError(
                f"Call Agent can only begin on a CONNECTED call (call is '{call.status}')"
            )

        brain_version, brain_config = await self._load_governance(call)

        config = await self.config_repo.get_for_business(call.business_id)
        if config is None:
            raise DomainError("Call Agent is not configured for this business")
        if call.call_type == CallType.TRANSACTIONAL.value:
            if not config.transactional_calling_enabled:
                raise DomainError("Transactional calling is disabled for this business")
        elif not config.marketing_calling_enabled:
            raise DomainError("Marketing calling is disabled for this business")

        if call.brain_version_id is None:
            call.brain_version_id = brain_version.id
            await self.lifecycle.call_repo.update(call)

        context = await self.build_context(call)
        instructions = self._build_instructions(call, brain_config, config, context)

        session_row = await self.lifecycle.start_session(call, language=language)
        session_row.conversation_log = [
            {"role": "system", "content": instructions, "at": _utcnow().isoformat()}
        ]
        await self.lifecycle.session_repo.update(session_row)

        logger.info(
            "voice_agent_session_begun",
            call_id=str(call.id),
            brain_version_id=str(brain_version.id),
        )
        return session_row

    # ── Context (deterministic, bounded projection) ──

    async def build_context(self, call: VoiceCall) -> dict:
        """Load bounded call context for instruction building.

        Only callers that already hold the call may build context —
        no authorization is bypassed here.  Projections are bounded
        to fields the agent is permitted to speak about.
        """
        context: dict = {
            "call_id": str(call.id),
            "call_type": call.call_type,
            "purpose": call.purpose,
            "to_number": call.to_number,
        }

        business = await self.session.get(Business, call.business_id)
        if business is not None:
            context["business_name"] = business.name

        if call.customer_id is not None:
            result = await self.session.execute(
                select(CustomerProfile).where(
                    CustomerProfile.user_id == call.customer_id,
                    CustomerProfile.deleted_at.is_(None),
                )
            )
            profile = result.scalars().first()
            if profile is not None:
                context["customer_name"] = f"{profile.first_name} {profile.last_name}"

        if call.enquiry_id is not None:
            from app.domain.enquiry.models import Enquiry

            enquiry = await self.session.get(Enquiry, call.enquiry_id)
            if enquiry is not None:
                context["enquiry"] = {
                    "reference": enquiry.reference,
                    "subject": enquiry.subject,
                    "status": enquiry.status,
                }

        if call.quote_id is not None:
            from app.domain.quote.models import Quote

            quote = await self.session.get(Quote, call.quote_id)
            if quote is not None:
                context["quote"] = {
                    "reference": quote.reference,
                    "amount": str(quote.amount),
                    "currency": quote.currency,
                    "status": quote.status,
                }

        if call.booking_id is not None:
            from app.domain.booking.models import Booking

            booking = await self.session.get(Booking, call.booking_id)
            if booking is not None:
                context["booking"] = {
                    "reference": booking.reference,
                    "currency": booking.currency,
                    "status": booking.status,
                }

        if call.invoice_id is not None:
            from app.domain.invoice.models import Invoice

            invoice = await self.session.get(Invoice, call.invoice_id)
            if invoice is not None:
                context["invoice"] = {
                    "invoice_number": invoice.invoice_number,
                    "total": str(invoice.total),
                    "currency": invoice.currency,
                    "payment_status": invoice.payment_status,
                }

        return context

    # ── Instructions (deterministic template) ──

    def _build_instructions(
        self,
        call: VoiceCall,
        brain_config: dict,
        config,
        context: dict,
    ) -> str:
        """Build agent instructions deterministically.

        Governance (Brain) supplies behavior authority: allowed
        actions, turn budget, collectible fields, escalation
        triggers.  Operational configuration may append style only.
        The AI is never granted state authority by instructions.
        """
        allowed_actions = self._allowed_actions(brain_config)
        collectible = self._collectible_fields(brain_config)
        max_turns = int(brain_config.get("max_turns", _DEFAULT_MAX_TURNS))
        escalation_triggers = brain_config.get("escalation_triggers") or []

        is_transactional = call.call_type == CallType.TRANSACTIONAL.value
        lines: list[str] = [
            f"You are the Call Agent for {context.get('business_name', 'the business')}.",
            (
                "This is a TRANSACTIONAL call about a specific service matter "
                f"(purpose: {call.purpose}).  Complete the task, collect only the "
                "governed information, and end the call."
                if is_transactional
                else "This is a MARKETING call (purpose: "
                f"{call.purpose}).  Follow the campaign script, respect the "
                "recipient's consent choices, and end the call politely if they "
                "are not interested.  You may never confirm bookings, prices, "
                "or payment arrangements."
            ),
            "",
            "Hard rules (never break):",
            "- Never quote prices, availability, or policies beyond the provided context.",
            "- Never promise or confirm bookings, changes, or payments — "
            "request a human for anything outside your scope.",
            "- Only request the governed collectible fields listed below.",
            "- If the caller asks for a human, or a trigger below applies, "
            "request a human immediately.",
            "",
            f"Allowed actions: {[a.value for a in allowed_actions]}",
            f"Maximum turns before forced handoff: {max_turns}",
            f"Collectible information fields: {sorted(collectible)}",
        ]
        if escalation_triggers:
            lines.append(f"Escalation triggers: {escalation_triggers}")

        if context.get("booking"):
            lines.append(f"Booking context: {context['booking']}")
        if context.get("quote"):
            lines.append(f"Quote context: {context['quote']}")
        if context.get("invoice"):
            lines.append(f"Invoice context: {context['invoice']}")
        if context.get("enquiry"):
            lines.append(f"Enquiry context: {context['enquiry']}")

        # Operational style supplement — never policy authority.
        if config is not None and config.agent_instructions:
            lines += ["", "Business style notes:", config.agent_instructions]

        return "\n".join(lines)

    # ── Turn handling ──

    async def handle_turn(
        self,
        call: VoiceCall,
        user_utterance: str,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> dict:
        """Handle one conversation turn.

        1. Require an active session; enforce the governed turn
           budget (forced handoff without consulting the AI).
        2. Obtain an AI proposal via the structured schema and
           validate it (fail-closed).
        3. Execute the action through deterministic services only.
        4. Audit the turn and any state-affecting action.
        """
        session_row = await self.lifecycle.session_repo.get_active_for_call(call.id)
        if session_row is None:
            raise StateTransitionError("No active conversation session for this call")

        _, brain_config = await self._load_governance(call)
        config = await self.config_repo.get_for_business(call.business_id)
        max_turns = int(brain_config.get("max_turns", _DEFAULT_MAX_TURNS))

        forced = session_row.turn_count >= max_turns
        if forced:
            # Turn budget exhausted — the AI is not consulted.  If
            # human escalation is available use it; otherwise the
            # agent must stop (deterministic NO_CONTACT outcome).
            if config is not None and config.human_escalation_enabled:
                proposal = {
                    "reply": (
                        "I have reached the limit of what I can help with on "
                        "this call.  Let me transfer you to a member of our "
                        "team."
                    ),
                    "action": AgentAction.REQUEST_HUMAN.value,
                    "collected_information": {},
                    "outcome": None,
                    "outcome_summary": None,
                    "escalation_reason": (f"Maximum conversation turns ({max_turns}) reached"),
                }
            else:
                proposal = {
                    "reply": (
                        "I have reached the limit of what I can help with on "
                        "this call.  Thank you for your time — goodbye."
                    ),
                    "action": AgentAction.END_CALL.value,
                    "collected_information": {},
                    "outcome": CallOutcome.NO_CONTACT.value,
                    "outcome_summary": f"Turn budget of {max_turns} reached",
                    "escalation_reason": None,
                }
        else:
            proposal = await self._propose(call, session_row, brain_config, user_utterance)

        action = AgentAction(proposal["action"])
        state_affecting = False

        if action is AgentAction.COLLECT_INFORMATION:
            self._apply_collected_information(session_row, brain_config, proposal)
        elif action is AgentAction.REQUEST_HUMAN:
            if config is None or not config.human_escalation_enabled:
                raise DomainError("Human escalation is disabled for this business")
        elif action is AgentAction.END_CALL:
            self._apply_outcome(session_row, call, proposal)

        log = list(session_row.conversation_log or [])
        log.append({"role": "customer", "content": user_utterance, "at": _utcnow().isoformat()})
        log.append(
            {
                "role": "agent",
                "content": proposal["reply"],
                "action": action.value,
                "forced": forced,
                "at": _utcnow().isoformat(),
            }
        )
        session_row.conversation_log = log
        session_row.turn_count += 1
        await self.lifecycle.session_repo.update(session_row)

        if action is AgentAction.REQUEST_HUMAN:
            state_affecting = True
            escalation_reason = proposal.get("escalation_reason") or "agent requested handoff"
            await self.lifecycle.escalate_call(
                call, escalation_reason=escalation_reason, actor_id=actor_id
            )
        elif action is AgentAction.END_CALL:
            state_affecting = True
            await self.lifecycle.complete_call(
                call,
                reason=f"agent ended call: {session_row.outcome}",
                actor_id=actor_id,
            )

        await self._audit_turn(call, action, session_row.turn_count, forced=forced)
        if state_affecting:
            await self._audit_action(call, action, session_row)

        return {
            "reply": proposal["reply"],
            "action": action.value,
            "outcome": proposal.get("outcome"),
            "turn_count": session_row.turn_count,
            "forced": forced,
            "session": session_row,
            "call": call,
        }

    # ── Deterministic outcome recording ──

    async def record_outcome(
        self,
        call: VoiceCall,
        outcome: str,
        summary: str | None = None,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> VoiceCallSession:
        """Record an outcome on the active session (human or agent)."""
        session_row = await self.lifecycle.session_repo.get_active_for_call(call.id)
        if session_row is None:
            raise StateTransitionError("No active conversation session for this call")

        try:
            parsed = CallOutcome(outcome)
        except ValueError as exc:
            raise DomainError(f"Unknown call outcome: '{outcome}'") from exc
        self._validate_outcome_for_call(call, parsed)

        session_row.outcome = parsed.value
        session_row.outcome_summary = summary
        await self.lifecycle.session_repo.update(session_row)

        await self._audit_action(call, AgentAction.END_CALL, session_row)
        return session_row

    # ── Governance ──

    async def _load_governance(self, call: VoiceCall) -> tuple[BrainVersion, dict]:
        """Load the ACTIVE BrainVersion and its voice_agent section.

        Closed-world: without an active governed brain and an
        explicit ``voice_agent`` section the agent must not run.
        """
        result = await self.session.execute(
            select(BrainVersion)
            .join(BusinessBrain, BusinessBrain.id == BrainVersion.brain_id)
            .where(
                BusinessBrain.business_id == call.business_id,
                BusinessBrain.active_version_id == BrainVersion.id,
                BrainVersion.status == "active",
                BrainVersion.deleted_at.is_(None),
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise DomainError(
                "No active Business Brain version found — the Call Agent cannot run ungoverned"
            )
        comm_config = version.communication_config or {}
        voice_agent = comm_config.get("voice_agent")
        if not isinstance(voice_agent, dict) or not voice_agent:
            raise DomainError(
                "Business Brain communication_config declares no 'voice_agent' "
                "section — the Call Agent cannot run"
            )
        return version, voice_agent

    @staticmethod
    def _allowed_actions(brain_config: dict) -> list[AgentAction]:
        """Governed action set (defaults to the full closed set)."""
        raw = brain_config.get("allowed_actions")
        if not raw:
            return list(AgentAction)
        try:
            allowed = [AgentAction(value) for value in raw]
        except ValueError as exc:
            raise DomainError(f"Business Brain declares unknown agent actions: {raw!r}") from exc
        if not allowed:
            raise DomainError("Business Brain allows no agent actions")
        return allowed

    @staticmethod
    def _collectible_fields(brain_config: dict) -> frozenset[str]:
        """Governed collectible fields (defaults to the safe set)."""
        raw = brain_config.get("collectible_fields")
        if not raw:
            from app.domain.common.enums import DEFAULT_COLLECTIBLE_FIELDS

            return DEFAULT_COLLECTIBLE_FIELDS
        return frozenset(str(field) for field in raw)

    # ── Proposal validation / application ──

    async def _propose(
        self,
        call: VoiceCall,
        session_row: VoiceCallSession,
        brain_config: dict,
        user_utterance: str,
    ) -> dict:
        """Obtain and validate an AI proposal for this turn."""
        context = await self.build_context(call)
        config = await self.config_repo.get_for_business(call.business_id)
        instructions = self._build_instructions(call, brain_config, config, context)

        transcript = [
            entry for entry in (session_row.conversation_log or []) if entry.get("role") != "system"
        ]
        prompt = (
            f"Conversation so far: {transcript}\n"
            f"Caller says: {user_utterance}\n"
            "Propose the next turn as JSON matching the schema."
        )
        proposal = await self.ai_provider.structured_output(
            prompt, AGENT_DECISION_SCHEMA, system=instructions
        )
        return self._validate_proposal(call, brain_config, proposal)

    def _validate_proposal(
        self,
        call: VoiceCall,
        brain_config: dict,
        proposal: Any,
    ) -> dict:
        """Fail-closed validation of an AI proposal."""
        if not isinstance(proposal, dict):
            raise DomainError("agent proposal rejected: not an object")

        reply = proposal.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            raise DomainError("agent proposal rejected: missing reply")

        raw_action = proposal.get("action")
        try:
            action = AgentAction(raw_action)
        except (ValueError, TypeError) as exc:
            raise DomainError(f"agent proposal rejected: unknown action {raw_action!r}") from exc
        if action not in self._allowed_actions(brain_config):
            raise DomainError(
                f"agent proposal rejected: action '{action.value}' is not "
                f"allowed by the Business Brain"
            )

        outcome = proposal.get("outcome")
        if outcome is not None:
            try:
                outcome_enum = CallOutcome(outcome)
            except (ValueError, TypeError) as exc:
                raise DomainError(f"agent proposal rejected: unknown outcome {outcome!r}") from exc
            self._validate_outcome_for_call(call, outcome_enum)

        collected = proposal.get("collected_information", {})
        if not isinstance(collected, dict):
            raise DomainError("agent proposal rejected: collected_information must be an object")

        return proposal

    def _apply_collected_information(
        self,
        session_row: VoiceCallSession,
        brain_config: dict,
        proposal: dict,
    ) -> None:
        """Merge governed information into the session (fail-closed)."""
        collectible = self._collectible_fields(brain_config)
        info = proposal.get("collected_information") or {}
        unknown = set(info) - set(collectible)
        if unknown:
            raise DomainError(f"agent attempted to collect non-governed fields: {sorted(unknown)}")
        merged = dict(session_row.collected_information or {})
        merged.update(info)
        session_row.collected_information = merged

    def _apply_outcome(
        self,
        session_row: VoiceCallSession,
        call: VoiceCall,
        proposal: dict,
    ) -> None:
        """Apply a validated END_CALL outcome to the session."""
        outcome = CallOutcome(proposal["outcome"])
        self._validate_outcome_for_call(call, outcome)
        session_row.outcome = outcome.value
        session_row.outcome_summary = proposal.get("outcome_summary")

    @staticmethod
    def _validate_outcome_for_call(call: VoiceCall, outcome: CallOutcome) -> None:
        """Transactional/marketing outcome separation (deterministic)."""
        if call.call_type == CallType.MARKETING.value and outcome in TRANSACTIONAL_ONLY_OUTCOMES:
            raise DomainError(
                f"Marketing calls may never record the transactional outcome '{outcome.value}'"
            )

    # ── Audit ──

    async def _audit_turn(
        self,
        call: VoiceCall,
        action: AgentAction,
        turn_count: int,
        *,
        forced: bool,
    ) -> None:
        evidence: dict = {
            "call_id": str(call.id),
            "call_type": call.call_type,
            "purpose": call.purpose,
            "action": action.value,
            "turn_count": turn_count,
            "forced": forced,
        }
        await self.audit_repo.create(
            CommunicationAuditEvent(
                event_type=AuditEventType.CALL_AGENT_TURN.value,
                business_id=call.business_id,
                customer_id=call.customer_id,
                channel=_AUDIT_CHANNEL,
                purpose=call.purpose,
                communication_id=call.communication_id,
                brain_version_id=call.brain_version_id,
                decision_evidence=evidence,
                metadata_=evidence,
            )
        )

    async def _audit_action(
        self,
        call: VoiceCall,
        action: AgentAction,
        session_row: VoiceCallSession,
    ) -> None:
        evidence: dict = {
            "call_id": str(call.id),
            "call_type": call.call_type,
            "purpose": call.purpose,
            "action": action.value,
            "outcome": session_row.outcome,
            "turn_count": session_row.turn_count,
        }
        await self.audit_repo.create(
            CommunicationAuditEvent(
                event_type=AuditEventType.CALL_AGENT_ACTION_EXECUTED.value,
                business_id=call.business_id,
                customer_id=call.customer_id,
                channel=_AUDIT_CHANNEL,
                purpose=call.purpose,
                communication_id=call.communication_id,
                brain_version_id=call.brain_version_id,
                decision_evidence=evidence,
                metadata_=evidence,
            )
        )
