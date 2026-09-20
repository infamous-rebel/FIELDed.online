"""Phase 14B.1 — Voice / Call Agent foundation tests against real PostgreSQL.

Covers:
- Schema verification (tables, columns, foreign keys, unique constraints)
- Call lifecycle (every valid transition path + representative invalid ones)
- Transactional vs marketing purpose/type gating (fail-closed configuration)
- Database-enforced idempotency per business
- Tenant isolation (cross-business access prevention at repository level)
- Optional relationship anchors (enquiry, quote, booking, execution, invoice,
  communication)
- Human escalation state transitions
- Campaign foundation lifecycle (no execution)
- Call Agent configuration (independent transactional/marketing enablement)

Phase 14A regression is NOT repeated here beyond what the full suite covers.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.domain.booking.models import Booking
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.common.enums import (
    CALL_PURPOSE_TYPE,
    CALL_SESSION_TRANSITIONS,
    CALL_TRANSITIONS,
    CAMPAIGN_RECIPIENT_TRANSITIONS,
    ESCALATION_TRANSITIONS,
    BookingStatus,
    CallPurpose,
    CallSessionStatus,
    CallStatus,
    CallType,
    CampaignRecipientStatus,
    CampaignStatus,
    EscalationStatus,
)
from app.domain.communication.models import (
    Communication,
    CommunicationAuditEvent,
)
from app.domain.enquiry.models import Enquiry
from app.domain.identity.models import Business, BusinessMember, User
from app.domain.invoice.models import Invoice
from app.domain.quote.models import Quote
from app.domain.service_execution.models import ServiceExecution
from app.domain.voice.campaign_service import CampaignService
from app.domain.voice.models import (
    CallAgentConfiguration,
    VoiceCall,
    VoiceCallSession,
)
from app.domain.voice.repository import (
    CallAgentConfigRepository,
    CampaignRecipientRepository,
    CampaignRepository,
    VoiceCallAttemptRepository,
    VoiceCallEscalationRepository,
    VoiceCallParticipantRepository,
    VoiceCallRepository,
    VoiceCallSessionRepository,
)
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import ConflictError, DomainError, StateTransitionError
from app.security.password import hash_password
from tests.factories import (
    business_factory,
    business_member_factory,
    service_category_factory,
    service_offer_factory,
)

PROVIDER = "twilio"


# ── Shared fixtures ──


@pytest_asyncio.fixture
async def biz_a(db_session: AsyncSession) -> tuple[User, Business, BusinessMember]:
    """Business A with an owner."""
    user = User(
        email=f"bizA-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    biz = business_factory(name="Voice Business A")
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    return user, biz, member


@pytest_asyncio.fixture
async def biz_b(db_session: AsyncSession) -> tuple[User, Business, BusinessMember]:
    """Business B with an owner (for tenant isolation tests)."""
    user = User(
        email=f"bizB-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    biz = business_factory(name="Voice Business B")
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    return user, biz, member


async def make_config(
    db_session: AsyncSession,
    business_id: uuid.UUID,
    **overrides,
) -> CallAgentConfiguration:
    """Create an enabled Call Agent configuration with both calling classes."""
    defaults = dict(
        business_id=business_id,
        enabled=True,
        transactional_calling_enabled=True,
        marketing_calling_enabled=True,
        default_from_number="+441234567890",
    )
    defaults.update(overrides)
    config = CallAgentConfiguration(**defaults)
    db_session.add(config)
    await db_session.flush()
    return config


async def request_call(
    db_session: AsyncSession,
    biz: Business,
    *,
    purpose: str = CallPurpose.BOOKING_REMINDER,
    with_config: bool = True,
    config_kwargs: dict | None = None,
    **kwargs,
) -> VoiceCall:
    """Request a call through the lifecycle service."""
    if with_config and config_kwargs is not None:
        await make_config(db_session, biz.id, **config_kwargs)
    elif with_config and config_kwargs is None:
        existing = await CallAgentConfigRepository(db_session).get_for_business(biz.id)
        if existing is None:
            await make_config(db_session, biz.id)

    service = VoiceCallLifecycleService(db_session)
    kwargs.setdefault("idempotency_key", f"call-{uuid.uuid4().hex}")
    return await service.request_call(
        business_id=biz.id,
        to_number="+447700900123",
        purpose=purpose,
        provider=PROVIDER,
        **kwargs,
    )


async def drive_call_to(
    lifecycle: VoiceCallLifecycleService,
    call: VoiceCall,
    target: CallStatus,
) -> VoiceCall:
    """Drive a call through valid transitions to the target status.

    Status-aware: steps already passed are skipped so the helper can
    resume driving a call from its current state.
    """
    order = [
        CallStatus.AUTHORIZED,
        CallStatus.QUEUED,
        CallStatus.INITIATING,
        CallStatus.RINGING,
        CallStatus.CONNECTED,
    ]
    steps = {
        CallStatus.AUTHORIZED: lifecycle.authorize_call,
        CallStatus.QUEUED: lifecycle.queue_call,
        CallStatus.INITIATING: lifecycle.mark_initiating,
        CallStatus.RINGING: lifecycle.mark_ringing,
        CallStatus.CONNECTED: lifecycle.mark_connected,
    }

    current = CallStatus(call.status)
    if current == target:
        return call
    current_idx = order.index(current) if current in order else -1

    for idx, status in enumerate(order):
        if idx <= current_idx:
            continue  # already passed this step
        await steps[status](call)
        if status == target:
            return call

    if target == CallStatus.IN_PROGRESS:
        await lifecycle.start_session(call)
        return call
    raise ValueError(f"Cannot drive call to {target}")


async def call_audit_events(
    db_session: AsyncSession, business_id: uuid.UUID
) -> list[CommunicationAuditEvent]:
    """All CALL_* audit events for a business.

    PostgreSQL ``now()`` is transaction-stable, so created_at is
    identical for every row written inside the test transaction —
    callers must assert on event-type multisets and per-type lookups,
    not on global created_at ordering.
    """
    result = await db_session.execute(
        select(CommunicationAuditEvent).where(
            CommunicationAuditEvent.business_id == business_id,
            CommunicationAuditEvent.event_type.like("CALL_%"),
        )
    )
    return list(result.scalars().all())


# ── 1. State machine invariants ──


class TestStateMachineInvariants:
    """The transition maps themselves must be deterministic and total."""

    def test_every_call_status_has_a_transition_entry(self):
        for status in CallStatus:
            assert status in CALL_TRANSITIONS

    def test_terminal_states_have_no_outgoing_transitions(self):
        terminal = [
            CallStatus.COMPLETED,
            CallStatus.FAILED,
            CallStatus.NO_ANSWER,
            CallStatus.BUSY,
            CallStatus.DECLINED,
            CallStatus.CANCELLED,
            CallStatus.EXPIRED,
            CallStatus.ESCALATED,
        ]
        for status in terminal:
            assert CALL_TRANSITIONS[status] == set(), status

    def test_all_transitions_target_declared_statuses(self):
        for _source, targets in CALL_TRANSITIONS.items():
            for target in targets:
                assert isinstance(target, CallStatus)
                assert target in CALL_TRANSITIONS

    def test_purpose_type_mapping_is_total(self):
        assert len(CALL_PURPOSE_TYPE) == len(list(CallPurpose))
        for purpose in CallPurpose:
            assert CALL_PURPOSE_TYPE[purpose] in (CallType.TRANSACTIONAL, CallType.MARKETING)

    def test_marketing_purposes_map_to_marketing_only(self):
        for purpose in (
            CallPurpose.SERVICE_PROMOTION,
            CallPurpose.EXISTING_CUSTOMER_CAMPAIGN,
            CallPurpose.LEAD_FOLLOW_UP,
            CallPurpose.REACTIVATION,
            CallPurpose.RENEWAL_REMINDER,
            CallPurpose.MARKETING_CAMPAIGN,
        ):
            assert CALL_PURPOSE_TYPE[purpose] == CallType.MARKETING

    def test_session_and_escalation_maps_are_total(self):
        for status in CallSessionStatus:
            assert status in CALL_SESSION_TRANSITIONS
        for status in EscalationStatus:
            assert status in ESCALATION_TRANSITIONS
        for status in CampaignRecipientStatus:
            assert status in CAMPAIGN_RECIPIENT_TRANSITIONS


# ── 2. Schema verification ──


class TestSchemaVerification:
    """Verify Phase 14B.1 tables, columns, foreign keys, and constraints."""

    async def test_voice_calls_table_exists(self, db_session: AsyncSession):
        result = await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'voice_calls' ORDER BY ordinal_position"
            )
        )
        cols = {r[0] for r in result.all()}
        required = {
            "id",
            "business_id",
            "customer_id",
            "enquiry_id",
            "quote_id",
            "booking_id",
            "service_execution_id",
            "invoice_id",
            "call_type",
            "purpose",
            "status",
            "to_number",
            "from_number",
            "provider",
            "provider_reference",
            "brain_version_id",
            "communication_id",
            "idempotency_key",
            "requested_at",
            "authorized_at",
            "queued_at",
            "initiated_at",
            "connected_at",
            "completed_at",
            "failed_at",
            "failure_code",
            "failure_reason",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        assert required.issubset(cols)

    async def test_child_tables_exist(self, db_session: AsyncSession):
        for table, cols in {
            "voice_call_participants": {
                "id",
                "call_id",
                "participant_type",
                "user_id",
                "customer_id",
                "business_member_id",
                "phone_number",
                "display_name",
                "role",
                "joined_at",
                "left_at",
            },
            "voice_call_attempts": {
                "id",
                "call_id",
                "attempt_number",
                "provider",
                "provider_reference",
                "status",
                "requested_at",
                "started_at",
                "connected_at",
                "completed_at",
                "failure_code",
                "failure_reason",
                "retryable",
                "provider_payload_reference",
            },
            "voice_call_sessions": {
                "id",
                "call_id",
                "session_status",
                "started_at",
                "ended_at",
                "agent_session_reference",
                "language",
                "transcript_reference",
                "recording_reference",
                "human_escalation_requested",
                "human_escalation_at",
            },
            "voice_call_escalations": {
                "id",
                "call_id",
                "escalation_status",
                "escalation_reason",
                "requested_at",
                "assigned_member_id",
                "accepted_at",
                "resolved_at",
                "resolution_notes",
            },
            "call_agent_configurations": {
                "id",
                "business_id",
                "enabled",
                "transactional_calling_enabled",
                "marketing_calling_enabled",
                "default_from_number",
                "provider_reference",
                "timezone",
                "max_attempts",
                "retry_interval_seconds",
                "allowed_calling_hours",
                "quiet_periods",
                "max_daily_attempts",
                "max_weekly_attempts",
                "customer_frequency_limits",
                "human_escalation_enabled",
                "recording_enabled",
                "transcription_enabled",
            },
            "communication_campaigns": {
                "id",
                "business_id",
                "name",
                "description",
                "channel",
                "purpose",
                "status",
                "start_at",
                "end_at",
                "brain_version_id",
                "created_by",
            },
            "campaign_recipients": {
                "id",
                "campaign_id",
                "customer_id",
                "phone_number",
                "status",
                "attempt_count",
                "last_attempt_at",
                "completed_at",
            },
        }.items():
            result = await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{table}'"
                )
            )
            found = {r[0] for r in result.all()}
            assert cols.issubset(found), f"{table} missing: {cols - found}"

    async def test_voice_calls_foreign_keys(self, db_session: AsyncSession):
        result = await db_session.execute(
            text(
                "SELECT ccu.table_name AS referenced_table "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.table_name = 'voice_calls' "
                "  AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        referenced = {r[0] for r in result.all()}
        expected = {
            "businesses",
            "users",
            "enquiries",
            "quotes",
            "bookings",
            "service_executions",
            "invoices",
            "brain_versions",
            "communications",
        }
        assert expected.issubset(referenced), f"missing FKs: {expected - referenced}"

    async def test_idempotency_unique_per_business(self, db_session: AsyncSession):
        result = await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_voice_calls_business_idempotency'"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert "voice_calls" in row
        assert "business_id" in row
        assert "idempotency_key" in row
        assert "UNIQUE" in row.upper()
        assert "deleted_at IS NULL" in row

    async def test_attempt_uniqueness_constraint(self, db_session: AsyncSession):
        result = await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_voice_call_attempts_call_attempt'"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert "call_id" in row and "attempt_number" in row
        assert "UNIQUE" in row.upper()

    async def test_config_unique_per_business(self, db_session: AsyncSession):
        result = await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_call_agent_configurations_business'"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert "business_id" in row
        assert "UNIQUE" in row.upper()
        assert "deleted_at IS NULL" in row


# ── 3. Call lifecycle ──


class TestCallLifecycle:
    """Every valid transition path plus representative invalid ones."""

    async def test_full_happy_path(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        assert call.status == CallStatus.REQUESTED.value
        assert call.call_type == CallType.TRANSACTIONAL.value
        assert call.requested_at is not None
        assert call.from_number == "+441234567890"

        lifecycle = VoiceCallLifecycleService(db_session)

        call = await lifecycle.authorize_call(call, reason="policy allow")
        assert call.status == CallStatus.AUTHORIZED.value
        assert call.authorized_at is not None

        call = await lifecycle.queue_call(call)
        assert call.status == CallStatus.QUEUED.value
        assert call.queued_at is not None

        call = await lifecycle.mark_initiating(call)
        assert call.status == CallStatus.INITIATING.value
        assert call.initiated_at is not None

        call = await lifecycle.mark_ringing(call)
        assert call.status == CallStatus.RINGING.value

        call = await lifecycle.mark_connected(call)
        assert call.status == CallStatus.CONNECTED.value
        assert call.connected_at is not None

        session_row = await lifecycle.start_session(call, language="en-GB")
        assert session_row.session_status == CallSessionStatus.ACTIVE.value
        assert session_row.started_at is not None
        assert session_row.ended_at is None
        assert call.status == CallStatus.IN_PROGRESS.value

        call = await lifecycle.complete_call(call)
        assert call.status == CallStatus.COMPLETED.value
        assert call.completed_at is not None

        await db_session.refresh(session_row)
        assert session_row.session_status == CallSessionStatus.COMPLETED.value
        assert session_row.ended_at is not None

    async def test_every_transition_produces_audit_evidence(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.IN_PROGRESS)
        await lifecycle.complete_call(call)

        events = await call_audit_events(db_session, biz.id)
        expected_multiset = {
            "CALL_REQUESTED": 1,
            "CALL_AUTHORIZED": 1,
            "CALL_QUEUED": 1,
            "CALL_INITIATED": 1,
            "CALL_RINGING": 1,
            "CALL_CONNECTED": 1,
            "CALL_SESSION_STARTED": 1,
            "CALL_IN_PROGRESS": 1,
            "CALL_COMPLETED": 1,
        }
        assert Counter(e.event_type for e in events) == Counter(expected_multiset)

        by_type = {e.event_type: e for e in events}
        requested = by_type["CALL_REQUESTED"]
        assert requested.metadata_["call_id"] == str(call.id)
        assert requested.metadata_["call_type"] == CallType.TRANSACTIONAL.value
        assert requested.metadata_["purpose"] == CallPurpose.BOOKING_REMINDER.value
        assert requested.metadata_["previous_status"] is None
        assert requested.metadata_["new_status"] == CallStatus.REQUESTED.value
        assert requested.channel == "VOICE"
        assert requested.brain_version_id is None

        completed = by_type["CALL_COMPLETED"]
        assert completed.metadata_["previous_status"] == CallStatus.IN_PROGRESS.value
        assert completed.metadata_["new_status"] == CallStatus.COMPLETED.value

    async def test_fail_call_from_ringing(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.RINGING)

        call = await lifecycle.fail_call(
            call, failure_code="PROVIDER_ERROR", failure_reason="trunk dropped"
        )
        assert call.status == CallStatus.FAILED.value
        assert call.failed_at is not None
        assert call.failure_code == "PROVIDER_ERROR"
        assert call.failure_reason == "trunk dropped"

    async def test_no_answer_and_busy_from_ringing(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        lifecycle = VoiceCallLifecycleService(db_session)

        call = await request_call(db_session, biz)
        await drive_call_to(lifecycle, call, CallStatus.RINGING)
        call = await lifecycle.mark_no_answer(call)
        assert call.status == CallStatus.NO_ANSWER.value

        other = await request_call(db_session, biz)
        await drive_call_to(lifecycle, other, CallStatus.RINGING)
        other = await lifecycle.mark_busy(other)
        assert other.status == CallStatus.BUSY.value

    async def test_cancel_from_queued(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await lifecycle.authorize_call(call)
        await lifecycle.queue_call(call)

        call = await lifecycle.cancel_call(call, reason="customer requested")
        assert call.status == CallStatus.CANCELLED.value

    async def test_expire_from_authorized(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await lifecycle.authorize_call(call)

        call = await lifecycle.expire_call(call)
        assert call.status == CallStatus.EXPIRED.value

    async def test_connect_then_immediate_complete(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.CONNECTED)

        # Short call: connected then completed without an agent session
        call = await lifecycle.complete_call(call)
        assert call.status == CallStatus.COMPLETED.value

    async def test_representative_invalid_transitions(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        lifecycle = VoiceCallLifecycleService(db_session)

        # REQUESTED -> CONNECTED (skipping the dialing path)
        call = await request_call(db_session, biz)
        with pytest.raises(StateTransitionError):
            await lifecycle.mark_connected(call)
        assert call.status == CallStatus.REQUESTED.value

        # RINGING -> COMPLETED (must pass through connected/in-progress)
        await drive_call_to(lifecycle, call, CallStatus.RINGING)
        with pytest.raises(StateTransitionError):
            await lifecycle.complete_call(call)
        assert call.status == CallStatus.RINGING.value

        # CANCELLED -> AUTHORIZED (terminal state)
        cancelled = await request_call(db_session, biz)
        await lifecycle.cancel_call(cancelled)
        with pytest.raises(StateTransitionError):
            await lifecycle.authorize_call(cancelled)
        assert cancelled.status == CallStatus.CANCELLED.value

        # COMPLETED -> QUEUED (terminal state)
        await drive_call_to(lifecycle, call, CallStatus.CONNECTED)
        completed = await lifecycle.complete_call(call)
        with pytest.raises(StateTransitionError):
            await lifecycle.queue_call(completed)
        assert completed.status == CallStatus.COMPLETED.value

    async def test_only_one_active_session_per_call(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.CONNECTED)
        await lifecycle.start_session(call)

        # Call is now IN_PROGRESS — starting another session is an
        # invalid call transition.
        with pytest.raises(StateTransitionError):
            await lifecycle.start_session(call)

        # Defensive guard: even if a call were anomally moved back to
        # CONNECTED with an active session, a duplicate session is
        # rejected instead of silently created.
        call.status = CallStatus.CONNECTED.value
        with pytest.raises(ConflictError):
            await lifecycle.start_session(call)

    async def test_fail_call_ends_active_session(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.IN_PROGRESS)

        call = await lifecycle.fail_call(call, failure_code="DROPPED")
        sessions = (
            (
                await db_session.execute(
                    select(VoiceCallSession).where(VoiceCallSession.call_id == call.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(sessions) == 1
        assert sessions[0].session_status == CallSessionStatus.FAILED.value
        assert sessions[0].ended_at is not None


# ── 4. Transactional vs marketing gating ──


class TestPurposeTypeGating:
    """Marketing must never enter the transactional path and vice versa."""

    async def test_marketing_purpose_cannot_be_transactional(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        with pytest.raises(DomainError):
            await request_call(
                db_session,
                biz,
                purpose=CallPurpose.SERVICE_PROMOTION,
                call_type=CallType.TRANSACTIONAL.value,
            )

    async def test_transactional_purpose_cannot_be_marketing(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        with pytest.raises(DomainError):
            await request_call(
                db_session,
                biz,
                purpose=CallPurpose.BOOKING_REMINDER,
                call_type=CallType.MARKETING.value,
            )

    async def test_marketing_call_blocked_when_marketing_disabled(
        self, db_session: AsyncSession, biz_a
    ):
        _, biz, _ = biz_a
        with pytest.raises(DomainError):
            await request_call(
                db_session,
                biz,
                purpose=CallPurpose.SERVICE_PROMOTION,
                config_kwargs={"marketing_calling_enabled": False},
            )

    async def test_transactional_call_blocked_when_transactional_disabled(
        self, db_session: AsyncSession, biz_a
    ):
        _, biz, _ = biz_a
        with pytest.raises(DomainError):
            await request_call(
                db_session,
                biz,
                purpose=CallPurpose.BOOKING_REMINDER,
                config_kwargs={"transactional_calling_enabled": False},
            )

    async def test_disabled_agent_blocks_all_calls(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        with pytest.raises(DomainError):
            await request_call(db_session, biz, config_kwargs={"enabled": False})

    async def test_missing_config_fails_closed(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        with pytest.raises(DomainError):
            await request_call(db_session, biz, with_config=False)

    async def test_existing_customer_marketing_call_stays_marketing(
        self, db_session: AsyncSession, biz_a
    ):
        user, biz, _ = biz_a
        # The recipient is an existing customer — the call must still be
        # classified MARKETING and require marketing enablement.
        call = await request_call(
            db_session,
            biz,
            purpose=CallPurpose.EXISTING_CUSTOMER_CAMPAIGN,
            customer_id=user.id,
        )
        assert call.call_type == CallType.MARKETING.value
        assert call.customer_id == user.id


# ── 5. Idempotency ──


class TestIdempotency:
    """Repeated logical call creation must not duplicate the call."""

    async def test_same_key_returns_same_call(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        key = f"booking-reminder:{uuid.uuid4().hex}"
        first = await request_call(db_session, biz, idempotency_key=key)
        second = await request_call(db_session, biz, idempotency_key=key)

        assert first.id == second.id
        count = (await db_session.execute(select(func.count()).select_from(VoiceCall))).scalar_one()
        assert count == 1

    async def test_different_key_creates_new_call(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        first = await request_call(db_session, biz, idempotency_key="k1")
        second = await request_call(db_session, biz, idempotency_key="k2")
        assert first.id != second.id

    async def test_same_key_different_business_is_independent(
        self, db_session: AsyncSession, biz_a, biz_b
    ):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b
        key = f"shared-key:{uuid.uuid4().hex}"
        call_a = await request_call(db_session, biz_a_row, idempotency_key=key)
        call_b = await request_call(db_session, biz_b_row, idempotency_key=key)
        assert call_a.id != call_b.id


# ── 6. Tenant isolation ──


class TestTenantIsolation:
    """One business cannot access another business's voice entities."""

    async def test_calls_are_tenant_scoped(self, db_session: AsyncSession, biz_a, biz_b):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        call = await request_call(db_session, biz_a_row)
        repo = VoiceCallRepository(db_session)

        assert await repo.get_by_id(call.id, business_id=biz_a_row.id) is not None
        assert await repo.get_by_id(call.id, business_id=biz_b_row.id) is None

        listed_b = await repo.list_for_business(biz_b_row.id)
        assert call not in listed_b

    async def test_attempts_are_tenant_scoped(self, db_session: AsyncSession, biz_a, biz_b):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        call = await request_call(db_session, biz_a_row)
        lifecycle = VoiceCallLifecycleService(db_session)
        attempt = await lifecycle.record_attempt(
            call, provider=PROVIDER, provider_reference="CA123"
        )

        attempt_repo = VoiceCallAttemptRepository(db_session)
        assert await attempt_repo.get_by_id(attempt.id, business_id=biz_a_row.id) is not None
        assert await attempt_repo.get_by_id(attempt.id, business_id=biz_b_row.id) is None

    async def test_sessions_are_tenant_scoped(self, db_session: AsyncSession, biz_a, biz_b):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        call = await request_call(db_session, biz_a_row)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.CONNECTED)
        session_row = await lifecycle.start_session(call)

        session_repo = VoiceCallSessionRepository(db_session)
        assert await session_repo.get_by_id(session_row.id, business_id=biz_a_row.id) is not None
        assert await session_repo.get_by_id(session_row.id, business_id=biz_b_row.id) is None

    async def test_escalations_are_tenant_scoped(self, db_session: AsyncSession, biz_a, biz_b):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        call = await request_call(db_session, biz_a_row)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.IN_PROGRESS)
        escalation = await lifecycle.escalate_call(
            call, escalation_reason="customer asked for a human"
        )

        escalation_repo = VoiceCallEscalationRepository(db_session)
        assert await escalation_repo.get_by_id(escalation.id, business_id=biz_a_row.id) is not None
        assert await escalation_repo.get_by_id(escalation.id, business_id=biz_b_row.id) is None

    async def test_participants_are_tenant_scoped(self, db_session: AsyncSession, biz_a, biz_b):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        call = await request_call(db_session, biz_a_row)
        lifecycle = VoiceCallLifecycleService(db_session)
        participant = await lifecycle.add_participant(
            call,
            participant_type="CUSTOMER",
            phone_number="+447700900123",
        )

        participant_repo = VoiceCallParticipantRepository(db_session)
        assert (
            await participant_repo.get_by_id(participant.id, business_id=biz_a_row.id) is not None
        )
        assert await participant_repo.get_by_id(participant.id, business_id=biz_b_row.id) is None

    async def test_configuration_is_tenant_scoped(self, db_session: AsyncSession, biz_a, biz_b):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        await make_config(db_session, biz_a_row.id)
        config_repo = CallAgentConfigRepository(db_session)
        assert await config_repo.get_for_business(biz_a_row.id) is not None
        assert await config_repo.get_for_business(biz_b_row.id) is None

    async def test_campaigns_and_recipients_are_tenant_scoped(
        self, db_session: AsyncSession, biz_a, biz_b
    ):
        _, biz_a_row, _ = biz_a
        _, biz_b_row, _ = biz_b

        campaign_service = CampaignService(db_session)
        campaign = await campaign_service.create_campaign(
            business_id=biz_a_row.id,
            name="Winter reactivation",
            channel="VOICE",
            purpose=CallPurpose.REACTIVATION.value,
        )
        recipient = await campaign_service.add_recipient(campaign, phone_number="+447700900999")

        campaign_repo = CampaignRepository(db_session)
        assert await campaign_repo.get_by_id(campaign.id, business_id=biz_a_row.id) is not None
        assert await campaign_repo.get_by_id(campaign.id, business_id=biz_b_row.id) is None

        recipient_repo = CampaignRecipientRepository(db_session)
        assert await recipient_repo.get_by_id(recipient.id, business_id=biz_a_row.id) is not None
        assert await recipient_repo.get_by_id(recipient.id, business_id=biz_b_row.id) is None


# ── 7. Relationships ──


class TestRelationships:
    """Valid optional relationship anchors persist and load."""

    @pytest_asyncio.fixture
    async def transaction_chain(self, db_session: AsyncSession, biz_a):
        """A full enquiry → quote → booking → execution → invoice chain."""
        user, biz, _ = biz_a
        category = service_category_factory()
        db_session.add(category)
        await db_session.flush()
        offer = service_offer_factory(business_id=biz.id)
        db_session.add(offer)
        await db_session.flush()

        enquiry = Enquiry(
            reference=f"ENQ-{uuid.uuid4().hex[:8]}",
            customer_id=user.id,
            business_id=biz.id,
            service_offer_id=offer.id,
            subject="Test enquiry",
            message="Please fix my boiler",
            status="booked",
        )
        db_session.add(enquiry)
        await db_session.flush()

        quote = Quote(
            reference=f"QUO-{uuid.uuid4().hex[:8]}",
            customer_id=user.id,
            business_id=biz.id,
            enquiry_id=enquiry.id,
            service_offer_id=offer.id,
            amount="100.00",
            currency="GBP",
            status="accepted",
        )
        db_session.add(quote)
        await db_session.flush()

        booking = Booking(
            reference=f"BKG-{uuid.uuid4().hex[:8]}",
            customer_id=user.id,
            business_id=biz.id,
            quote_id=quote.id,
            enquiry_id=enquiry.id,
            service_offer_id=offer.id,
            requested_at=datetime.now(UTC) + timedelta(days=2),
            currency="GBP",
            status=BookingStatus.CONFIRMED,
        )
        db_session.add(booking)
        await db_session.flush()

        execution = ServiceExecution(
            business_id=biz.id,
            customer_id=user.id,
            booking_id=booking.id,
            service_offer_id=offer.id,
            status="scheduled",
        )
        db_session.add(execution)
        await db_session.flush()

        invoice = Invoice(
            business_id=biz.id,
            customer_id=user.id,
            service_execution_id=execution.id,
            booking_id=booking.id,
            quote_id=quote.id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            issue_date=datetime.now(UTC),
            currency="GBP",
        )
        db_session.add(invoice)
        await db_session.flush()

        return {
            "user": user,
            "biz": biz,
            "enquiry": enquiry,
            "quote": quote,
            "booking": booking,
            "execution": execution,
            "invoice": invoice,
        }

    async def test_call_with_all_relationship_anchors(
        self, db_session: AsyncSession, biz_a, transaction_chain
    ):
        chain = transaction_chain
        biz = chain["biz"]

        communication = Communication(
            business_id=biz.id,
            customer_id=chain["user"].id,
            channel="VOICE",
            purpose=CallPurpose.BOOKING_REMINDER.value,
            idempotency_key=f"comm-{uuid.uuid4().hex}",
        )
        db_session.add(communication)
        await db_session.flush()

        brain = BusinessBrain(business_id=biz.id)
        db_session.add(brain)
        await db_session.flush()
        brain_version = BrainVersion(brain_id=brain.id, version_number=1, status="active")
        db_session.add(brain_version)
        await db_session.flush()

        call = await request_call(
            db_session,
            biz,
            customer_id=chain["user"].id,
            enquiry_id=chain["enquiry"].id,
            quote_id=chain["quote"].id,
            booking_id=chain["booking"].id,
            service_execution_id=chain["execution"].id,
            invoice_id=chain["invoice"].id,
            communication_id=communication.id,
            brain_version_id=brain_version.id,
        )

        # Re-fetch the Phase 14A integration anchors with eager loading
        loaded = (
            await db_session.execute(
                select(VoiceCall)
                .where(VoiceCall.id == call.id)
                .options(
                    joinedload(VoiceCall.communication),
                    joinedload(VoiceCall.brain_version),
                )
            )
        ).scalar_one()

        # Every optional anchor is queryable — an inner join across all
        # of them matches exactly the one call row (referential integrity)
        joined_count = (
            await db_session.execute(
                select(func.count())
                .select_from(VoiceCall)
                .join(Enquiry, VoiceCall.enquiry_id == Enquiry.id)
                .join(Quote, VoiceCall.quote_id == Quote.id)
                .join(Booking, VoiceCall.booking_id == Booking.id)
                .join(
                    ServiceExecution,
                    VoiceCall.service_execution_id == ServiceExecution.id,
                )
                .join(Invoice, VoiceCall.invoice_id == Invoice.id)
                .join(Communication, VoiceCall.communication_id == Communication.id)
                .where(VoiceCall.id == call.id)
            )
        ).scalar_one()
        assert joined_count == 1

        assert call.enquiry_id == chain["enquiry"].id
        assert call.quote_id == chain["quote"].id
        assert call.booking_id == chain["booking"].id
        assert call.service_execution_id == chain["execution"].id
        assert call.invoice_id == chain["invoice"].id
        assert call.communication_id == communication.id
        assert call.brain_version_id == brain_version.id

        assert loaded.communication.id == communication.id
        assert loaded.brain_version.id == brain_version.id
        assert loaded.communication.channel == "VOICE"

    async def test_call_with_no_relationship_anchors(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        assert call.enquiry_id is None
        assert call.quote_id is None
        assert call.booking_id is None
        assert call.service_execution_id is None
        assert call.invoice_id is None
        assert call.communication_id is None
        assert call.customer_id is None

    async def test_participant_types_supported(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)

        customer_participant = await lifecycle.add_participant(
            call, participant_type="CUSTOMER", phone_number="+447700900123"
        )
        agent_participant = await lifecycle.add_participant(
            call,
            participant_type="AGENT",
            phone_number="+441234567890",
            display_name="FIELDed Call Agent",
        )
        external_participant = await lifecycle.add_participant(
            call,
            participant_type="EXTERNAL",
            phone_number="+447700900555",
        )

        # A phone number alone is a legitimate external participant
        assert external_participant.user_id is None
        assert external_participant.customer_id is None
        assert external_participant.business_member_id is None

        participants = await VoiceCallParticipantRepository(db_session).list_for_call(call.id)
        assert {p.participant_type for p in participants} == {
            "CUSTOMER",
            "AGENT",
            "EXTERNAL",
        }
        assert customer_participant.call_id == call.id
        assert agent_participant.display_name == "FIELDed Call Agent"


# ── 8. Attempts ──


class TestCallAttempts:
    """Attempts are append-oriented and uniquely numbered per call."""

    async def test_attempt_numbers_are_sequential_and_unique(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)

        first = await lifecycle.record_attempt(
            call,
            provider=PROVIDER,
            status="NO_ANSWER",
            failure_code="NO_ANSWER",
            retryable=True,
        )
        second = await lifecycle.record_attempt(
            call,
            provider=PROVIDER,
            status="FAILED",
            failure_code="TRUNK_ERROR",
            retryable=True,
        )

        assert first.attempt_number == 1
        assert second.attempt_number == 2
        assert first.id != second.id

        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert [a.attempt_number for a in attempts] == [1, 2]
        assert attempts[0].status == "NO_ANSWER"  # history preserved


# ── 9. Escalation ──


class TestEscalation:
    """Human escalation state transitions."""

    async def test_full_escalation_lifecycle(self, db_session: AsyncSession, biz_a):
        user, biz, member = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.IN_PROGRESS)

        escalation = await lifecycle.escalate_call(
            call, escalation_reason="customer requested a human"
        )
        assert escalation.escalation_status == EscalationStatus.REQUESTED.value
        assert escalation.requested_at is not None
        assert call.status == CallStatus.ESCALATED.value

        escalation = await lifecycle.assign_escalation(escalation, assigned_member_id=member.id)
        assert escalation.escalation_status == EscalationStatus.ASSIGNED.value
        assert escalation.assigned_member_id == member.id

        escalation = await lifecycle.accept_escalation(escalation)
        assert escalation.escalation_status == EscalationStatus.ACCEPTED.value
        assert escalation.accepted_at is not None

        escalation = await lifecycle.resolve_escalation(
            escalation, resolution_notes="resolved with the customer"
        )
        assert escalation.escalation_status == EscalationStatus.RESOLVED.value
        assert escalation.resolved_at is not None
        assert escalation.resolution_notes == "resolved with the customer"

    async def test_cancel_escalation(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.CONNECTED)

        escalation = await lifecycle.escalate_call(call, escalation_reason="unclear request")
        escalation = await lifecycle.cancel_escalation(
            escalation, reason="customer changed their mind"
        )
        assert escalation.escalation_status == EscalationStatus.CANCELLED.value

    async def test_invalid_escalation_transition(self, db_session: AsyncSession, biz_a):
        _, biz, member = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.CONNECTED)

        escalation = await lifecycle.escalate_call(call, escalation_reason="unclear request")
        with pytest.raises(StateTransitionError):
            await lifecycle.accept_escalation(escalation)  # REQUESTED -> ACCEPTED
        assert escalation.escalation_status == EscalationStatus.REQUESTED.value

    async def test_escalation_requires_active_call_state(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        # Call is only REQUESTED — escalation is not a valid transition
        with pytest.raises(StateTransitionError):
            await lifecycle.escalate_call(call, escalation_reason="too early")

    async def test_escalated_session_is_marked(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        call = await request_call(db_session, biz)
        lifecycle = VoiceCallLifecycleService(db_session)
        await drive_call_to(lifecycle, call, CallStatus.IN_PROGRESS)

        session_row = (
            await db_session.execute(
                select(VoiceCallSession).where(VoiceCallSession.call_id == call.id)
            )
        ).scalar_one()

        await lifecycle.escalate_call(call, escalation_reason="complex case")
        await db_session.refresh(session_row)
        assert session_row.human_escalation_requested is True
        assert session_row.human_escalation_at is not None
        assert session_row.session_status == CallSessionStatus.ESCALATED.value
        assert session_row.ended_at is not None


# ── 10. Campaign foundation ──


class TestCampaignFoundation:
    """Campaign lifecycle only — execution is a later 14B block."""

    async def test_campaign_lifecycle(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        service = CampaignService(db_session)
        campaign = await service.create_campaign(
            business_id=biz.id,
            name="Winter boiler service push",
            channel="VOICE",
            purpose=CallPurpose.SERVICE_PROMOTION.value,
        )
        assert campaign.status == CampaignStatus.DRAFT.value
        assert campaign.business_id == biz.id

        campaign = await service.transition_campaign(campaign, CampaignStatus.SCHEDULED)
        assert campaign.status == CampaignStatus.SCHEDULED.value

        campaign = await service.transition_campaign(campaign, CampaignStatus.ACTIVE)
        assert campaign.status == CampaignStatus.ACTIVE.value

        campaign = await service.transition_campaign(campaign, CampaignStatus.PAUSED)
        assert campaign.status == CampaignStatus.PAUSED.value

        campaign = await service.transition_campaign(campaign, CampaignStatus.ACTIVE)
        assert campaign.status == CampaignStatus.ACTIVE.value

        campaign = await service.transition_campaign(campaign, CampaignStatus.COMPLETED)
        assert campaign.status == CampaignStatus.COMPLETED.value

    async def test_campaign_invalid_transitions(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        service = CampaignService(db_session)
        campaign = await service.create_campaign(
            business_id=biz.id,
            name="Draft only",
            channel="VOICE",
            purpose=CallPurpose.MARKETING_CAMPAIGN.value,
        )

        with pytest.raises(StateTransitionError):
            await service.transition_campaign(campaign, CampaignStatus.COMPLETED)

        cancelled = await service.transition_campaign(campaign, CampaignStatus.CANCELLED)
        with pytest.raises(StateTransitionError):
            await service.transition_campaign(cancelled, CampaignStatus.ACTIVE)

    async def test_recipient_status_transitions(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        service = CampaignService(db_session)
        campaign = await service.create_campaign(
            business_id=biz.id,
            name="Service reminders",
            channel="VOICE",
            purpose=CallPurpose.RENEWAL_REMINDER.value,
        )
        recipient = await service.add_recipient(campaign, phone_number="+447700900999")
        assert recipient.status == CampaignRecipientStatus.PENDING.value
        assert recipient.attempt_count == 0

        recipient = await service.transition_recipient(recipient, CampaignRecipientStatus.ELIGIBLE)
        assert recipient.status == CampaignRecipientStatus.ELIGIBLE.value

        recipient = await service.transition_recipient(recipient, CampaignRecipientStatus.CONTACTED)
        assert recipient.attempt_count == 1
        assert recipient.last_attempt_at is not None

        recipient = await service.transition_recipient(recipient, CampaignRecipientStatus.COMPLETED)
        assert recipient.completed_at is not None

    async def test_recipient_invalid_transition(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        service = CampaignService(db_session)
        campaign = await service.create_campaign(
            business_id=biz.id,
            name="Service reminders",
            channel="VOICE",
            purpose=CallPurpose.RENEWAL_REMINDER.value,
        )
        recipient = await service.add_recipient(campaign, phone_number="+447700900999")
        with pytest.raises(StateTransitionError):
            await service.transition_recipient(recipient, CampaignRecipientStatus.CONTACTED)
        assert recipient.status == CampaignRecipientStatus.PENDING.value


# ── 11. Call Agent configuration ──


class TestCallAgentConfiguration:
    """Independent transactional / marketing enablement and upsert."""

    async def test_transactional_only_config(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        await make_config(
            db_session,
            biz.id,
            transactional_calling_enabled=True,
            marketing_calling_enabled=False,
        )
        # Transactional works
        call = await request_call(
            db_session,
            biz,
            purpose=CallPurpose.BOOKING_REMINDER,
            with_config=False,
        )
        assert call.call_type == CallType.TRANSACTIONAL.value

        # Marketing is rejected
        with pytest.raises(DomainError):
            await request_call(
                db_session,
                biz,
                purpose=CallPurpose.SERVICE_PROMOTION,
                with_config=False,
            )

    async def test_marketing_only_config(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        await make_config(
            db_session,
            biz.id,
            transactional_calling_enabled=False,
            marketing_calling_enabled=True,
        )
        # Marketing works
        call = await request_call(
            db_session,
            biz,
            purpose=CallPurpose.SERVICE_PROMOTION,
            with_config=False,
        )
        assert call.call_type == CallType.MARKETING.value

        # Transactional is rejected
        with pytest.raises(DomainError):
            await request_call(
                db_session,
                biz,
                purpose=CallPurpose.BOOKING_REMINDER,
                with_config=False,
            )

    async def test_config_upsert_updates_existing(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        config_repo = CallAgentConfigRepository(db_session)
        original = await make_config(db_session, biz.id)

        updated = CallAgentConfiguration(
            business_id=biz.id,
            enabled=False,
            max_attempts=5,
            retry_interval_seconds=600,
        )
        result = await config_repo.upsert(updated)

        assert result.id == original.id
        assert result.enabled is False
        assert result.max_attempts == 5
        assert result.retry_interval_seconds == 600
        # Unspecified fields are preserved
        assert result.transactional_calling_enabled is True

        configs = (
            (
                await db_session.execute(
                    select(CallAgentConfiguration).where(
                        CallAgentConfiguration.business_id == biz.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(configs) == 1

    async def test_config_defaults_are_fail_closed(self, db_session: AsyncSession, biz_a):
        _, biz, _ = biz_a
        config = CallAgentConfiguration(business_id=biz.id)
        db_session.add(config)
        await db_session.flush()

        assert config.enabled is False
        assert config.transactional_calling_enabled is False
        assert config.marketing_calling_enabled is False
