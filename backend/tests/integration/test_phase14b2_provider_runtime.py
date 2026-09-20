"""Phase 14B.2 Block A — voice provider orchestration runtime tests.

Covers (targeted per implementation block):
- Successful initiation: provider reference persisted on call + attempt,
  call stays INITIATING, audit evidence present
- Idempotent re-initiation (no double dial)
- Retryable provider failure: call stays INITIATING; retry after the
  configured interval appends attempt #2; retry before the interval is
  rejected
- Attempts exhausted fails the call (MAX_ATTEMPTS_EXCEEDED)
- Non-retryable provider failure fails the call
- Initiation from invalid states raises StateTransitionError
- Provider state synchronization (ringing / completed two-step /
  connection failures from INITIATING / terminal no-ops / unknown status)
- Tenant isolation at the repository boundary

All provider interactions use an in-memory stub — never the network.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.domain.common.enums import AuditEventType, CallPurpose, CallStatus
from app.domain.communication.models import CommunicationAuditEvent
from app.domain.identity.models import Business, User
from app.domain.voice.models import CallAgentConfiguration, VoiceCall
from app.domain.voice.provider_service import (
    PROVIDER_STATUS_TRANSITIONS,
    VoiceProviderOrchestrationService,
)
from app.domain.voice.repository import (
    VoiceCallAttemptRepository,
    VoiceCallRepository,
)
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import DomainError, StateTransitionError
from app.security.password import hash_password
from tests.factories import business_factory, business_member_factory

PROVIDER = "stub"


# ── Stub provider ──


class StubVoiceProvider(VoiceProvider):
    """Deterministic in-memory voice provider.

    Returns queued results in order; when the queue is empty, every
    dial succeeds with a fresh generated reference.  Records every
    request for assertions.
    """

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
    biz = business_factory(name="Provider Business A")
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    return biz


@pytest_asyncio.fixture
async def biz_b(db_session: AsyncSession) -> Business:
    """Business B with an owner (tenant isolation)."""
    user = User(
        email=f"bizB-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    biz = business_factory(name="Provider Business B")
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
    """Create an enabled Call Agent configuration with both classes."""
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


async def authorized_call(
    db_session: AsyncSession,
    biz: Business,
    *,
    purpose: str = CallPurpose.BOOKING_REMINDER,
    config_kwargs: dict | None = None,
    **kwargs,
) -> tuple[VoiceCall, VoiceCallLifecycleService, CallAgentConfiguration]:
    """Create a configured call and drive it to AUTHORIZED."""
    config = await make_config(db_session, biz.id, **(config_kwargs or {}))
    lifecycle = VoiceCallLifecycleService(db_session)
    kwargs.setdefault("idempotency_key", f"call-{uuid.uuid4().hex}")
    call = await lifecycle.request_call(
        business_id=biz.id,
        to_number="+447700900123",
        purpose=purpose,
        provider=PROVIDER,
        **kwargs,
    )
    call = await lifecycle.authorize_call(call)
    return call, lifecycle, config


def orchestration_for(
    db_session: AsyncSession,
    provider: StubVoiceProvider,
) -> VoiceProviderOrchestrationService:
    return VoiceProviderOrchestrationService(db_session, provider)


async def call_audit_events(
    db_session: AsyncSession,
    business_id: uuid.UUID,
) -> list[CommunicationAuditEvent]:
    """All CALL_% audit events for a business.

    Assertions use Counter multisets, not row ordering — PostgreSQL
    now() is transaction-stable so created_at cannot disambiguate.
    """
    result = await db_session.execute(
        select(CommunicationAuditEvent).where(
            CommunicationAuditEvent.business_id == business_id,
            CommunicationAuditEvent.event_type.like("CALL_%"),
        )
    )
    return list(result.scalars().all())


# ── 1. Provider status mapping ──


class TestProviderStatusMap:
    def test_map_is_total_over_documented_provider_statuses(self):
        assert set(PROVIDER_STATUS_TRANSITIONS) == {
            "ringing",
            "in-progress",
            "completed",
            "busy",
            "no-answer",
            "failed",
            "canceled",
            "declined",
        }

    def test_every_mapped_value_is_a_call_status(self):
        for value in PROVIDER_STATUS_TRANSITIONS.values():
            assert CallStatus(value)  # raises on unknown values


# ── 2. Initiation ──


class TestInitiateCallSuccess:
    async def test_success_persists_reference_and_stays_initiating(self, db_session, biz_a):
        provider = StubVoiceProvider()
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(db_session, biz_a)

        result = await service.initiate_call(call)

        assert result.id == call.id
        assert result.status == CallStatus.INITIATING.value
        assert result.provider_reference is not None
        assert len(provider.requests) == 1
        assert provider.requests[0].to == "+447700900123"
        assert provider.requests[0].from_number == "+441234567890"
        assert provider.requests[0].metadata["call_id"] == str(call.id)
        assert provider.requests[0].metadata["business_id"] == str(biz_a.id)
        assert provider.requests[0].metadata["purpose"] == CallPurpose.BOOKING_REMINDER

        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].provider == PROVIDER
        assert attempts[0].provider_reference == result.provider_reference
        assert attempts[0].status == "DIALED"
        assert attempts[0].started_at is not None

        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_QUEUED.value] == 1
        assert types[AuditEventType.CALL_INITIATED.value] == 1
        assert types[AuditEventType.CALL_PROVIDER_STATE_SYNC.value] == 1

    async def test_re_initiation_is_idempotent(self, db_session, biz_a):
        provider = StubVoiceProvider()
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(db_session, biz_a)

        first = await service.initiate_call(call)
        second = await service.initiate_call(call)

        assert second.id == first.id
        assert second.provider_reference == first.provider_reference
        assert len(provider.requests) == 1
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert len(attempts) == 1


class TestRetryableFailure:
    async def test_retryable_failure_keeps_call_initiating(self, db_session, biz_a):
        provider = StubVoiceProvider(
            [ProviderResult.failure("provider temporarily unavailable", retryable=True)]
        )
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(db_session, biz_a)

        result = await service.initiate_call(call)

        assert result.status == CallStatus.INITIATING.value
        assert result.provider_reference is None
        assert result.failure_code is None  # call itself has not failed

        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert len(attempts) == 1
        assert attempts[0].status == CallStatus.FAILED.value
        assert attempts[0].retryable is True
        assert attempts[0].failure_code == "PROVIDER_ERROR"
        assert attempts[0].failure_reason == "provider temporarily unavailable"

    async def test_retry_before_interval_raises(self, db_session, biz_a):
        provider = StubVoiceProvider([ProviderResult.failure("temporary outage", retryable=True)])
        service = orchestration_for(db_session, provider)
        call, _, config = await authorized_call(db_session, biz_a)
        await service.initiate_call(call)

        with pytest.raises(DomainError, match="retry interval"):
            await service.initiate_call(call)

        # No extra dial happened.
        assert len(provider.requests) == 1
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert len(attempts) == 1
        assert config.retry_interval_seconds > 0

    async def test_retry_after_interval_creates_second_attempt(self, db_session, biz_a):
        provider = StubVoiceProvider([ProviderResult.failure("temporary outage", retryable=True)])
        service = orchestration_for(db_session, provider)
        call, _, config = await authorized_call(db_session, biz_a)
        await service.initiate_call(call)

        attempt_repo = VoiceCallAttemptRepository(db_session)
        attempts = await attempt_repo.list_for_call(call.id)
        attempts[0].requested_at = datetime.now(UTC) - timedelta(
            seconds=config.retry_interval_seconds + 1
        )
        await db_session.flush()

        provider.results.append(ProviderResult.ok("CA-second-attempt"))
        retried = await service.initiate_call(call)

        assert retried.status == CallStatus.INITIATING.value
        assert retried.provider_reference == "CA-second-attempt"
        attempts = await attempt_repo.list_for_call(call.id)
        assert len(attempts) == 2
        assert attempts[1].attempt_number == 2
        assert attempts[1].provider_reference == "CA-second-attempt"
        assert attempts[1].status == "DIALED"
        assert len(provider.requests) == 2


# ── 3. Attempt limits / terminal failures ──


class TestAttemptExhaustion:
    async def test_attempts_exhausted_fails_call(self, db_session, biz_a):
        provider = StubVoiceProvider([ProviderResult.failure("temporary outage", retryable=True)])
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(
            db_session,
            biz_a,
            config_kwargs={"max_attempts": 1, "retry_interval_seconds": 0},
        )
        await service.initiate_call(call)  # attempt 1: retryable failure

        failed = await service.initiate_call(call)  # 1 attempt >= max 1

        assert failed.status == CallStatus.FAILED.value
        assert failed.failure_code == "MAX_ATTEMPTS_EXCEEDED"
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert len(attempts) == 1  # no extra dial occurred


class TestNonRetryableFailure:
    async def test_non_retryable_failure_fails_call(self, db_session, biz_a):
        provider = StubVoiceProvider(
            [ProviderResult.failure("invalid phone number", retryable=False)]
        )
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(db_session, biz_a)

        result = await service.initiate_call(call)

        assert result.status == CallStatus.FAILED.value
        assert result.failure_code == "PROVIDER_ERROR"
        assert result.failure_reason == "invalid phone number"
        assert result.failed_at is not None

        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert attempts[0].status == CallStatus.FAILED.value
        assert attempts[0].retryable is False

        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_FAILED.value] == 1


# ── 4. Invalid initiation states ──


class TestInitiateInvalidState:
    async def test_initiate_from_requested_raises(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        lifecycle = VoiceCallLifecycleService(db_session)
        call = await lifecycle.request_call(
            business_id=biz_a.id,
            to_number="+447700900123",
            purpose=CallPurpose.BOOKING_REMINDER,
            provider=PROVIDER,
            idempotency_key=f"call-{uuid.uuid4().hex}",
        )
        service = orchestration_for(db_session, StubVoiceProvider())

        with pytest.raises(StateTransitionError):
            await service.initiate_call(call)

    async def test_initiate_from_terminal_state_raises(self, db_session, biz_a):
        call, lifecycle, _ = await authorized_call(db_session, biz_a)
        call = await lifecycle.cancel_call(call, reason="no longer needed")
        service = orchestration_for(db_session, StubVoiceProvider())

        with pytest.raises(StateTransitionError):
            await service.initiate_call(call)

    async def test_initiate_after_ring_progression_raises(self, db_session, biz_a):
        """Once the provider reports ringing, re-dialing is forbidden."""
        provider = StubVoiceProvider()
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(db_session, biz_a)
        call = await service.initiate_call(call)
        call = await service.sync_provider_status(call, "ringing")
        assert call.status == CallStatus.RINGING.value

        with pytest.raises(StateTransitionError):
            await service.initiate_call(call)


# ── 5. Provider state synchronization ──


class TestSyncProviderStatus:
    async def _initiated_call(
        self, db_session, biz
    ) -> tuple[VoiceCall, VoiceProviderOrchestrationService]:
        provider = StubVoiceProvider()
        service = orchestration_for(db_session, provider)
        call, _, _ = await authorized_call(db_session, biz)
        call = await service.initiate_call(call)
        return call, service

    async def test_sync_ringing_from_initiating(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)

        synced = await service.sync_provider_status(call, "ringing")

        assert synced.status == CallStatus.RINGING.value
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert attempts[-1].status == CallStatus.RINGING.value
        assert attempts[-1].started_at is not None

    async def test_sync_completed_from_ringing_is_two_step(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)
        call = await service.sync_provider_status(call, "ringing")

        synced = await service.sync_provider_status(call, "completed")

        # Deterministic pre-step: connect first, then complete.
        assert synced.status == CallStatus.COMPLETED.value
        assert synced.connected_at is not None
        assert synced.completed_at is not None
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert attempts[-1].status == CallStatus.COMPLETED.value
        assert attempts[-1].connected_at is not None
        assert attempts[-1].completed_at is not None

    async def test_sync_completed_from_in_progress(self, db_session, biz_a):
        call, lifecycle, _ = await authorized_call(db_session, biz_a)
        provider = StubVoiceProvider()
        service = orchestration_for(db_session, provider)
        call = await service.initiate_call(call)
        call = await service.sync_provider_status(call, "ringing")
        call = await service.sync_provider_status(call, "in-progress")
        assert call.status == CallStatus.CONNECTED.value
        session_row = await lifecycle.start_session(call)

        synced = await service.sync_provider_status(call, "completed")

        assert synced.status == CallStatus.COMPLETED.value
        assert session_row.session_status == "COMPLETED"
        assert session_row.ended_at is not None

    async def test_sync_busy_from_initiating_fails_call(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)

        synced = await service.sync_provider_status(call, "busy")

        # Deterministic pre-step: busy is unreachable from INITIATING.
        assert synced.status == CallStatus.FAILED.value
        assert synced.failure_code == CallStatus.BUSY.value
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        # The attempt records provider truth ('BUSY'); the call models
        # the deterministic outcome (FAILED).
        assert attempts[-1].status == CallStatus.BUSY.value
        assert attempts[-1].failure_code == CallStatus.BUSY.value

    async def test_sync_no_answer_from_ringing(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)
        call = await service.sync_provider_status(call, "ringing")

        synced = await service.sync_provider_status(call, "no-answer")

        assert synced.status == CallStatus.NO_ANSWER.value
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert attempts[-1].status == CallStatus.NO_ANSWER.value

    async def test_sync_declined_from_ringing(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)
        call = await service.sync_provider_status(call, "ringing")

        synced = await service.sync_provider_status(call, "declined")

        assert synced.status == CallStatus.DECLINED.value

    async def test_sync_failed_from_in_progress(self, db_session, biz_a):
        call, lifecycle, _ = await authorized_call(db_session, biz_a)
        service = orchestration_for(db_session, StubVoiceProvider())
        call = await service.initiate_call(call)
        call = await service.sync_provider_status(call, "ringing")
        call = await service.sync_provider_status(call, "in-progress")
        session_row = await lifecycle.start_session(call)

        synced = await service.sync_provider_status(call, "failed")

        assert synced.status == CallStatus.FAILED.value
        assert synced.failure_code == "PROVIDER_FAILED"
        assert session_row.session_status == "FAILED"

    async def test_sync_canceled_from_initiating(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)

        synced = await service.sync_provider_status(call, "canceled")

        assert synced.status == CallStatus.CANCELLED.value

    async def test_sync_repeated_event_is_noop(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)
        call = await service.sync_provider_status(call, "ringing")

        synced = await service.sync_provider_status(call, "ringing")

        assert synced.status == CallStatus.RINGING.value

    async def test_sync_terminal_call_is_noop(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)
        call = await service.sync_provider_status(call, "ringing")
        call = await service.sync_provider_status(call, "completed")
        assert call.status == CallStatus.COMPLETED.value

        synced = await service.sync_provider_status(call, "ringing")

        assert synced.status == CallStatus.COMPLETED.value

    async def test_sync_unknown_status_raises(self, db_session, biz_a):
        call, service = await self._initiated_call(db_session, biz_a)

        with pytest.raises(DomainError, match="Unknown provider call status"):
            await service.sync_provider_status(call, "smoke-signals")


# ── 6. Tenant isolation ──


class TestTenantIsolation:
    async def test_cross_business_scoped_fetch_returns_none(self, db_session, biz_a, biz_b):
        """A call is only obtainable through its owning business."""
        call, _, _ = await authorized_call(db_session, biz_a)
        repo = VoiceCallRepository(db_session)

        assert await repo.get_by_id(call.id, business_id=biz_b.id) is None
        assert await repo.get_by_id(call.id, business_id=biz_a.id) is not None
