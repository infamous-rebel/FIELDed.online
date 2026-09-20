"""Phase 14B.2 Block C — Call Agent runtime & conversation tests.

Covers (targeted per implementation block):
- Governed session start (closed-world: ACTIVE brain + voice_agent
  section required; brain_version_id traced on the call; CONNECTED
  required; calling-class enablement re-checked)
- Deterministic instruction building (purpose class + allowed
  actions present in the AI system prompt; operational style only)
- Turn loop: CONTINUE, governed COLLECT_INFORMATION (non-governed
  fields rejected), REQUEST_HUMAN (gated by config), END_CALL with
  outcome validation
- Transactional vs marketing outcome separation
- Turn-budget exhaustion forces handoff WITHOUT consulting the AI
- Malformed/disallowed AI proposals rejected (fail-closed, no state
  change)
- Deterministic outcome recording for human-completed sessions
- Audit per turn and per state-affecting action
"""

from __future__ import annotations

import uuid
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AIProvider
from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.common.enums import AuditEventType, CallPurpose, CallStatus
from app.domain.communication.models import CommunicationAuditEvent
from app.domain.identity.models import Business, User
from app.domain.voice.agent import VoiceCallAgent
from app.domain.voice.models import CallAgentConfiguration, VoiceCall
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import DomainError, StateTransitionError
from app.security.password import hash_password
from tests.factories import business_factory, business_member_factory

PROVIDER = "stub"


# ── Stubs ──


class StubVoiceProvider(VoiceProvider):
    """Deterministic in-memory voice provider (never network)."""

    def __init__(self, results: list[ProviderResult] | None = None) -> None:
        self.results = list(results or [])
        self.requests: list[VoiceCallRequest] = []

    @property
    def provider_name(self) -> str:
        return PROVIDER

    async def initiate_call(self, request: VoiceCallRequest) -> ProviderResult:
        self.requests.append(request)
        if self.results:
            return self.results.pop(0)
        return ProviderResult.ok(f"CA{uuid.uuid4().hex[:24]}")


class StubAIProvider(AIProvider):
    """Deterministic AI provider returning queued proposals."""

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    @property
    def provider_name(self) -> str:
        return "stub"

    async def complete(self, prompt, *, system=None, max_tokens=4096, temperature=0.7):
        raise AssertionError("complete() is not used by the Call Agent")

    async def structured_output(self, prompt, schema, *, system=None, max_tokens=4096):
        self.calls.append({"prompt": prompt, "system": system, "schema": schema})
        if self.responses:
            return self.responses.pop(0)
        return {
            "reply": "Understood.",
            "action": "CONTINUE",
            "collected_information": {},
            "outcome": None,
            "outcome_summary": None,
            "escalation_reason": None,
        }


# ── Governed voice_agent configuration ──

VOICE_AGENT_CONFIG = {
    "max_turns": 3,
    "collectible_fields": ["callback_number", "preferred_time"],
    "allowed_actions": [
        "CONTINUE",
        "COLLECT_INFORMATION",
        "REQUEST_HUMAN",
        "END_CALL",
    ],
    "escalation_triggers": ["customer requests human"],
}


# ── Shared fixtures / helpers ──


@pytest_asyncio.fixture
async def biz_a(db_session: AsyncSession) -> Business:
    """Business A with an owner."""
    user = User(
        email=f"bizA-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    biz = business_factory(name="Agent Business A")
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    return biz


async def make_config(
    db_session: AsyncSession,
    business_id: uuid.UUID,
    **overrides,
) -> CallAgentConfiguration:
    defaults = dict(
        business_id=business_id,
        enabled=True,
        transactional_calling_enabled=True,
        marketing_calling_enabled=True,
        default_from_number="+441234567890",
        human_escalation_enabled=True,
    )
    defaults.update(overrides)
    config = CallAgentConfiguration(**defaults)
    db_session.add(config)
    await db_session.flush()
    return config


async def make_brain(
    db_session: AsyncSession,
    biz: Business,
    *,
    voice_agent: dict | None = None,
    include_voice_agent: bool = True,
) -> BrainVersion:
    """Active BusinessBrain + BrainVersion for the business."""
    brain = BusinessBrain(business_id=biz.id)
    db_session.add(brain)
    await db_session.flush()
    communication_config = (
        {"voice_agent": voice_agent or VOICE_AGENT_CONFIG} if include_voice_agent else {}
    )
    version = BrainVersion(
        brain_id=brain.id,
        version_number=1,
        status="active",
        communication_config=communication_config,
    )
    db_session.add(version)
    await db_session.flush()
    brain.active_version_id = version.id
    await db_session.flush()
    return version


async def connected_call(
    db_session: AsyncSession,
    biz: Business,
    *,
    purpose: str = CallPurpose.BOOKING_REMINDER,
    config_kwargs: dict | None = None,
) -> tuple[VoiceCall, VoiceCallLifecycleService, CallAgentConfiguration]:
    """Configured call dialed and synced to CONNECTED."""
    config = await make_config(db_session, biz.id, **(config_kwargs or {}))
    lifecycle = VoiceCallLifecycleService(db_session)
    orchestration = VoiceProviderOrchestrationService(db_session, StubVoiceProvider())
    call = await lifecycle.request_call(
        business_id=biz.id,
        to_number="+447700900123",
        purpose=purpose,
        provider=PROVIDER,
        idempotency_key=f"call-{uuid.uuid4().hex}",
    )
    call = await lifecycle.authorize_call(call)
    call = await orchestration.initiate_call(call)
    call = await orchestration.sync_provider_status(call, "ringing")
    call = await orchestration.sync_provider_status(call, "in-progress")
    return call, lifecycle, config


def agent_for(db_session: AsyncSession, ai: StubAIProvider) -> VoiceCallAgent:
    return VoiceCallAgent(db_session, ai)


async def begin_session(
    db_session: AsyncSession,
    biz: Business,
) -> tuple[VoiceCall, VoiceCallAgent, StubAIProvider, BrainVersion]:
    """Connected call + governed agent session already begun."""
    call, _, _ = await connected_call(db_session, biz)
    version = await make_brain(db_session, biz)
    ai = StubAIProvider()
    agent = agent_for(db_session, ai)
    await agent.begin(call)
    return call, agent, ai, version


async def call_audit_events(
    db_session: AsyncSession,
    business_id: uuid.UUID,
) -> list[CommunicationAuditEvent]:
    result = await db_session.execute(
        select(CommunicationAuditEvent).where(
            CommunicationAuditEvent.business_id == business_id,
            CommunicationAuditEvent.event_type.like("CALL_%"),
        )
    )
    return list(result.scalars().all())


# ── 1. Governed session start ──


class TestAgentBegin:
    async def test_begin_creates_session_and_governance_trace(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        version = await make_brain(db_session, biz_a)
        agent = agent_for(db_session, StubAIProvider())

        session_row = await agent.begin(call)

        assert session_row.session_status == "ACTIVE"
        assert call.status == CallStatus.IN_PROGRESS.value
        assert call.brain_version_id == version.id
        assert session_row.conversation_log[0]["role"] == "system"
        assert "COLLECT_INFORMATION" in session_row.conversation_log[0]["content"]
        assert session_row.turn_count == 0

        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_SESSION_STARTED.value] == 1

    async def test_begin_requires_active_brain(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        agent = agent_for(db_session, StubAIProvider())

        with pytest.raises(DomainError, match="cannot run ungoverned"):
            await agent.begin(call)

    async def test_begin_requires_voice_agent_section(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        await make_brain(db_session, biz_a, include_voice_agent=False)
        agent = agent_for(db_session, StubAIProvider())

        with pytest.raises(DomainError, match="voice_agent"):
            await agent.begin(call)

    async def test_begin_requires_connected_call(self, db_session, biz_a):
        """The agent cannot begin on a call that never connected."""
        await make_config(db_session, biz_a.id)
        lifecycle = VoiceCallLifecycleService(db_session)
        orchestration = VoiceProviderOrchestrationService(db_session, StubVoiceProvider())
        call = await lifecycle.request_call(
            business_id=biz_a.id,
            to_number="+447700900123",
            purpose=CallPurpose.BOOKING_REMINDER,
            provider=PROVIDER,
            idempotency_key=f"call-{uuid.uuid4().hex}",
        )
        call = await lifecycle.authorize_call(call)
        call = await orchestration.initiate_call(call)
        assert call.status == CallStatus.INITIATING.value

        await make_brain(db_session, biz_a)
        agent = agent_for(db_session, StubAIProvider())

        with pytest.raises(StateTransitionError):
            await agent.begin(call)

    async def test_begin_rechecks_class_enablement(self, db_session, biz_a):
        call, _, config = await connected_call(db_session, biz_a)
        await make_brain(db_session, biz_a)
        config.transactional_calling_enabled = False
        await db_session.flush()
        agent = agent_for(db_session, StubAIProvider())

        with pytest.raises(DomainError, match="Transactional calling is disabled"):
            await agent.begin(call)


# ── 2. Turn handling ──


class TestAgentTurns:
    async def test_continue_turn_appends_log_and_audits(self, db_session, biz_a):
        call, agent, ai, _ = await begin_session(db_session, biz_a)

        result = await agent.handle_turn(call, "Hello, who is this?")

        assert result["action"] == "CONTINUE"
        assert result["turn_count"] == 1
        assert len(ai.calls) == 1
        session_row = result["session"]
        roles = [entry["role"] for entry in session_row.conversation_log]
        assert roles == ["system", "customer", "agent"]

        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_AGENT_TURN.value] == 1

    async def test_collect_information_stores_governed_fields(self, db_session, biz_a):
        call, agent, ai, _ = await begin_session(db_session, biz_a)
        ai.responses.append(
            {
                "reply": "Could I take a callback number?",
                "action": "COLLECT_INFORMATION",
                "collected_information": {
                    "callback_number": "+447700900999",
                    "preferred_time": "mornings",
                },
                "outcome": None,
                "outcome_summary": None,
                "escalation_reason": None,
            }
        )

        result = await agent.handle_turn(call, "Anytime really")

        session_row = result["session"]
        assert session_row.collected_information == {
            "callback_number": "+447700900999",
            "preferred_time": "mornings",
        }

    async def test_collect_information_rejects_non_governed_fields(self, db_session, biz_a):
        call, agent, ai, _ = await begin_session(db_session, biz_a)
        ai.responses.append(
            {
                "reply": "Noted.",
                "action": "COLLECT_INFORMATION",
                "collected_information": {"credit_card": "4111111111111111"},
                "outcome": None,
                "outcome_summary": None,
                "escalation_reason": None,
            }
        )

        with pytest.raises(DomainError, match="non-governed"):
            await agent.handle_turn(call, "Here is my card number")

        session_row = await agent.lifecycle.session_repo.get_active_for_call(call.id)
        assert session_row.collected_information is None
        assert session_row.turn_count == 0

    async def test_request_human_escalates(self, db_session, biz_a):
        call, agent, ai, _ = await begin_session(db_session, biz_a)
        ai.responses.append(
            {
                "reply": "Let me transfer you to our team.",
                "action": "REQUEST_HUMAN",
                "collected_information": {},
                "outcome": None,
                "outcome_summary": None,
                "escalation_reason": "customer requests human",
            }
        )

        await agent.handle_turn(call, "I want to talk to a person")

        assert call.status == CallStatus.ESCALATED.value
        session_row = await agent.lifecycle.session_repo.get_active_for_call(call.id)
        assert session_row is None  # ended (ESCALATED)
        escalation = await agent.lifecycle.escalation_repo.get_for_call(call.id)
        assert escalation is not None
        assert escalation.escalation_status == "REQUESTED"
        assert escalation.escalation_reason == "customer requests human"

        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_AGENT_ACTION_EXECUTED.value] == 1
        assert types[AuditEventType.CALL_ESCALATED.value] == 1

    async def test_request_human_disabled_raises(self, db_session, biz_a):
        call, _, _ = await connected_call(
            db_session, biz_a, config_kwargs={"human_escalation_enabled": False}
        )
        await make_brain(db_session, biz_a)
        ai = StubAIProvider(
            responses=[
                {
                    "reply": "Transferring.",
                    "action": "REQUEST_HUMAN",
                    "collected_information": {},
                    "outcome": None,
                    "outcome_summary": None,
                    "escalation_reason": "customer requests human",
                }
            ]
        )
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        with pytest.raises(DomainError, match="escalation is disabled"):
            await agent.handle_turn(call, "I want a human")

    async def test_end_call_completes_with_outcome(self, db_session, biz_a):
        call, agent, ai, _ = await begin_session(db_session, biz_a)
        ai.responses.append(
            {
                "reply": "Great, your booking is confirmed. Goodbye.",
                "action": "END_CALL",
                "collected_information": {},
                "outcome": "CONFIRMED",
                "outcome_summary": "Recipient confirmed the booking",
                "escalation_reason": None,
            }
        )

        result = await agent.handle_turn(call, "Yes, that all sounds right")

        assert call.status == CallStatus.COMPLETED.value
        session_row = result["session"]
        assert session_row.outcome == "CONFIRMED"
        assert session_row.outcome_summary == "Recipient confirmed the booking"
        assert session_row.session_status == "COMPLETED"

    async def test_marketing_call_cannot_record_transactional_outcome(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a, purpose=CallPurpose.SERVICE_PROMOTION)
        await make_brain(db_session, biz_a)
        ai = StubAIProvider(
            responses=[
                {
                    "reply": "Confirmed!",
                    "action": "END_CALL",
                    "collected_information": {},
                    "outcome": "CONFIRMED",
                    "outcome_summary": None,
                    "escalation_reason": None,
                }
            ]
        )
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        with pytest.raises(DomainError, match="transactional outcome"):
            await agent.handle_turn(call, "Sounds good to me")

        assert call.status == CallStatus.IN_PROGRESS.value

    async def test_marketing_call_information_collected_ok(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a, purpose=CallPurpose.SERVICE_PROMOTION)
        await make_brain(db_session, biz_a)
        ai = StubAIProvider(
            responses=[
                {
                    "reply": "Noted, thank you. Goodbye.",
                    "action": "END_CALL",
                    "collected_information": {},
                    "outcome": "INFORMATION_COLLECTED",
                    "outcome_summary": "Interest noted",
                    "escalation_reason": None,
                }
            ]
        )
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        await agent.handle_turn(call, "Maybe send me details")

        assert call.status == CallStatus.COMPLETED.value

    async def test_max_turns_forces_handoff_without_ai(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        await make_brain(
            db_session, biz_a, voice_agent={**VOICE_AGENT_CONFIG, "max_turns": 2}
        )
        ai = StubAIProvider()
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        await agent.handle_turn(call, "one")
        await agent.handle_turn(call, "two")
        assert len(ai.calls) == 2

        result = await agent.handle_turn(call, "three")

        assert result["forced"] is True
        assert result["action"] == "REQUEST_HUMAN"
        assert len(ai.calls) == 2  # AI was NOT consulted on the forced turn
        assert call.status == CallStatus.ESCALATED.value
        escalation = await agent.lifecycle.escalation_repo.get_for_call(call.id)
        assert escalation is not None
        assert "Maximum conversation turns" in escalation.escalation_reason

    async def test_max_turns_forced_end_when_escalation_disabled(self, db_session, biz_a):
        call, _, _ = await connected_call(
            db_session,
            biz_a,
            config_kwargs={"human_escalation_enabled": False},
        )
        await make_brain(db_session, biz_a, voice_agent={**VOICE_AGENT_CONFIG, "max_turns": 1})
        ai = StubAIProvider()
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        await agent.handle_turn(call, "one")
        result = await agent.handle_turn(call, "two")

        assert result["forced"] is True
        assert result["action"] == "END_CALL"
        assert result["outcome"] == "NO_CONTACT"
        assert call.status == CallStatus.COMPLETED.value

    async def test_malformed_proposal_rejected_without_state_change(self, db_session, biz_a):
        call, agent, ai, _ = await begin_session(db_session, biz_a)
        ai.responses.append({"reply": "Moving money", "action": "TRANSFER_MONEY"})

        with pytest.raises(DomainError, match="agent proposal rejected"):
            await agent.handle_turn(call, "do something")

        session_row = await agent.lifecycle.session_repo.get_active_for_call(call.id)
        assert session_row.turn_count == 0
        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_AGENT_TURN.value] == 0

    async def test_disallowed_action_rejected(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        await make_brain(
            db_session,
            biz_a,
            voice_agent={**VOICE_AGENT_CONFIG, "allowed_actions": ["CONTINUE", "END_CALL"]},
        )
        ai = StubAIProvider(
            responses=[
                {
                    "reply": "Transferring.",
                    "action": "REQUEST_HUMAN",
                    "collected_information": {},
                    "outcome": None,
                    "outcome_summary": None,
                    "escalation_reason": "customer requests human",
                }
            ]
        )
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        with pytest.raises(DomainError, match="not allowed"):
            await agent.handle_turn(call, "I want a human")

    async def test_turn_without_session_raises(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        await make_brain(db_session, biz_a)
        agent = agent_for(db_session, StubAIProvider())

        with pytest.raises(StateTransitionError, match="No active conversation"):
            await agent.handle_turn(call, "hello")


# ── 3. Instruction authority provenance ──


class TestInstructionAuthority:
    async def test_instructions_contain_purpose_class_and_actions(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        await make_brain(db_session, biz_a)
        ai = StubAIProvider()
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        await agent.handle_turn(call, "hello")

        system = ai.calls[0]["system"]
        assert "TRANSACTIONAL" in system
        assert "COLLECT_INFORMATION" in system
        assert "Never quote prices" in system

    async def test_marketing_instructions_contain_marketing_class(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a, purpose=CallPurpose.SERVICE_PROMOTION)
        await make_brain(db_session, biz_a)
        ai = StubAIProvider()
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        await agent.handle_turn(call, "hello")

        system = ai.calls[0]["system"]
        assert "MARKETING" in system
        assert "may never confirm bookings" in system

    async def test_operational_agent_instructions_appended_as_style(self, db_session, biz_a):
        call, _, config = await connected_call(
            db_session, biz_a, config_kwargs={"agent_instructions": "Speak warmly."}
        )
        await make_brain(db_session, biz_a)
        ai = StubAIProvider()
        agent = agent_for(db_session, ai)
        await agent.begin(call)

        await agent.handle_turn(call, "hello")

        system = ai.calls[0]["system"]
        assert "Speak warmly." in system
        assert "Business style notes" in system


# ── 4. Deterministic outcome recording ──


class TestRecordOutcome:
    async def test_record_outcome_on_active_session(self, db_session, biz_a):
        call, agent, _, _ = await begin_session(db_session, biz_a)

        session_row = await agent.record_outcome(
            call, "CALLBACK_REQUESTED", "Recipient asked for an evening callback"
        )

        assert session_row.outcome == "CALLBACK_REQUESTED"
        assert session_row.outcome_summary == ("Recipient asked for an evening callback")
        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_AGENT_ACTION_EXECUTED.value] == 1

    async def test_record_outcome_marketing_restriction(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a, purpose=CallPurpose.SERVICE_PROMOTION)
        await make_brain(db_session, biz_a)
        agent = agent_for(db_session, StubAIProvider())
        await agent.begin(call)

        with pytest.raises(DomainError, match="transactional outcome"):
            await agent.record_outcome(call, "PAYMENT_ARRANGED")

    async def test_record_outcome_unknown_value(self, db_session, biz_a):
        call, agent, _, _ = await begin_session(db_session, biz_a)

        with pytest.raises(DomainError, match="Unknown call outcome"):
            await agent.record_outcome(call, "SOMETHING_HAPPENED")

    async def test_record_outcome_requires_session(self, db_session, biz_a):
        call, _, _ = await connected_call(db_session, biz_a)
        await make_brain(db_session, biz_a)
        agent = agent_for(db_session, StubAIProvider())

        with pytest.raises(StateTransitionError, match="No active conversation"):
            await agent.record_outcome(call, "OTHER")
