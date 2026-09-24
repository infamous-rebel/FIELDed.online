"""Phase 14B.2 Block D — campaign execution tests.

Covers (targeted per implementation block):
- Governed activation: marketing campaigns require a Brain version;
  start_at is a hard scheduling gate
- Calling-window enforcement: allowed hours, quiet periods, timezone
- Closed-world policy gating: consent/DNC → SUPPRESSED,
  missing governance → SKIPPED (never silent ALLOW)
- Frequency limits: attempt budget exhaustion → FAILED, throughput
  caps → SKIPPED
- Processing: ALLOW recipients get exactly one VoiceCall per attempt
  (idempotency key format, campaign/brain linkage, source)
- Re-runs never duplicate calls for already-CONTACTED recipients
- Marketing vs transactional separation through the policy chain
  (transactional bypasses consent; marketing requires opt-in)
- Outcome settlement: COMPLETED → recipient COMPLETED + campaign
  auto-complete; terminal failure → FAILED; ESCALATED keeps
  recipient CONTACTED (human owns the outcome)
- Cancellation between runs leaves PENDING recipients untouched
- Campaign audit provenance (processing started / suppressed / skipped)
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.common.enums import (
    AuditEventType,
    CallPurpose,
    CallStatus,
    CallType,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.domain.communication.models import (
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    CommunicationAuditEvent,
    CustomerCommunicationPreference,
)
from app.domain.communication.repository import (
    CommunicationConfigRepository,
    ConsentRepository,
)
from app.domain.identity.models import Business, User
from app.domain.voice.campaign_execution import CampaignExecutionService
from app.domain.voice.campaign_service import CampaignService
from app.domain.voice.models import (
    CallAgentConfiguration,
    CommunicationCampaign,
    VoiceCall,
)
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import DomainError, StateTransitionError
from app.security.password import hash_password
from tests.factories import business_factory

PROVIDER = "stub"

# Monday 2026-06-15, 12:00 UTC — inside any default calling window.
NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


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
        return ProviderResult.ok(f"CP{uuid.uuid4().hex[:24]}")


# ── Shared fixtures / helpers ──


@pytest_asyncio.fixture
async def biz_a(db_session: AsyncSession) -> Business:
    """Business A."""
    biz = business_factory(name="Campaign Business A")
    db_session.add(biz)
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
) -> BrainVersion:
    """Active BusinessBrain + BrainVersion (no timing/frequency rules)."""
    brain = BusinessBrain(business_id=biz.id)
    db_session.add(brain)
    await db_session.flush()
    version = BrainVersion(
        brain_id=brain.id,
        version_number=1,
        status="active",
        communication_config={"timing_rules": {}, "frequency_rules": {}},
    )
    db_session.add(version)
    await db_session.flush()
    brain.active_version_id = version.id
    await db_session.flush()
    return version


async def setup_voice_policy(db_session: AsyncSession, biz: Business) -> None:
    """VOICE channel + MARKETING/TRANSACTIONAL purpose config enabled."""
    repo = CommunicationConfigRepository(db_session)
    await repo.upsert_channel_config(
        BusinessCommunicationChannel(
            business_id=biz.id,
            channel="VOICE",
            enabled=True,
            provider_ref="stub",
        )
    )
    await repo.upsert_purpose_config(
        BusinessCommunicationPurpose(
            business_id=biz.id,
            purpose="MARKETING",
            enabled=True,
            permitted_channels=["VOICE"],
        )
    )
    await repo.upsert_purpose_config(
        BusinessCommunicationPurpose(
            business_id=biz.id,
            purpose="TRANSACTIONAL",
            enabled=True,
            permitted_channels=["VOICE"],
        )
    )
    await db_session.flush()


async def make_customer(
    db_session: AsyncSession,
    biz: Business,
    *,
    opt_in: bool = True,
    do_not_contact: bool = False,
    with_preference: bool = True,
) -> User:
    """A customer user; consent preference is VOICE/MARKETING scoped."""
    user = User(
        email=f"cust-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    if with_preference:
        consent_state = "DNC" if do_not_contact else ("OPTED_IN" if opt_in else "UNKNOWN")
        await ConsentRepository(db_session).upsert(
            CustomerCommunicationPreference(
                customer_id=user.id,
                business_id=biz.id,
                channel="VOICE",
                purpose="MARKETING",
                consent_state=consent_state,
                opt_in=opt_in and not do_not_contact,
                do_not_contact=do_not_contact,
                source="test",
                consented_at=NOW if opt_in and not do_not_contact else None,
            )
        )
    return user


async def make_campaign(
    db_session: AsyncSession,
    biz: Business,
    *,
    purpose: str = CallPurpose.SERVICE_PROMOTION.value,
    brain_version_id: uuid.UUID | None = None,
    start_at: datetime | None = None,
    name: str = "June campaign",
) -> tuple[CommunicationCampaign, CampaignService]:
    campaigns = CampaignService(db_session)
    campaign = await campaigns.create_campaign(
        business_id=biz.id,
        name=name,
        channel="VOICE",
        purpose=purpose,
        start_at=start_at,
        brain_version_id=brain_version_id,
    )
    return campaign, campaigns


def execution_for(db_session: AsyncSession, provider: StubVoiceProvider):
    return CampaignExecutionService(db_session, provider)


async def voice_calls_for(db_session: AsyncSession, business_id: uuid.UUID) -> list[VoiceCall]:
    result = await db_session.execute(
        select(VoiceCall).where(VoiceCall.business_id == business_id).order_by(VoiceCall.created_at.asc())
    )
    return list(result.scalars().all())


async def campaign_audit_events(
    db_session: AsyncSession,
    business_id: uuid.UUID,
    *,
    event_type_prefix: str = "CAMPAIGN_%",
) -> list[CommunicationAuditEvent]:
    result = await db_session.execute(
        select(CommunicationAuditEvent).where(
            CommunicationAuditEvent.business_id == business_id,
            CommunicationAuditEvent.event_type.like(event_type_prefix),
        )
    )
    return list(result.scalars().all())


# ── 1. Governed activation ──


class TestActivation:
    async def test_marketing_activation_requires_brain_version(self, db_session, biz_a):
        campaign, _ = await make_campaign(db_session, biz_a)
        execution = execution_for(db_session, StubVoiceProvider())

        with pytest.raises(DomainError, match="governing Brain version"):
            await execution.activate(campaign)

        assert campaign.status == CampaignStatus.DRAFT.value

    async def test_marketing_activation_with_brain_version(self, db_session, biz_a):
        version = await make_brain(db_session, biz_a)
        campaign, _ = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        execution = execution_for(db_session, StubVoiceProvider())

        result = await execution.activate(campaign)

        assert result.status == CampaignStatus.ACTIVE.value

    async def test_transactional_activation_without_brain(self, db_session, biz_a):
        campaign, _ = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        execution = execution_for(db_session, StubVoiceProvider())

        result = await execution.activate(campaign)

        assert result.status == CampaignStatus.ACTIVE.value

    async def test_activation_before_start_at_raises(self, db_session, biz_a):
        campaign, _ = await make_campaign(
            db_session,
            biz_a,
            purpose=CallPurpose.BOOKING_REMINDER.value,
            start_at=NOW.replace(hour=13),
        )
        execution = execution_for(db_session, StubVoiceProvider())

        with pytest.raises(DomainError, match="start_at"):
            await execution.activate(campaign, now=NOW)

        assert campaign.status == CampaignStatus.DRAFT.value

    async def test_activation_after_start_at_activates(self, db_session, biz_a):
        campaign, _ = await make_campaign(
            db_session,
            biz_a,
            purpose=CallPurpose.BOOKING_REMINDER.value,
            start_at=NOW.replace(hour=11),
        )
        execution = execution_for(db_session, StubVoiceProvider())

        result = await execution.activate(campaign, now=NOW)

        assert result.status == CampaignStatus.ACTIVE.value


# ── 2. Calling-window enforcement ──


class TestCallingWindow:
    async def test_outside_allowed_hours_skips(self, db_session, biz_a):
        await make_config(
            db_session,
            biz_a.id,
            allowed_calling_hours={
                "days": [0, 1, 2, 3, 4, 5, 6],
                "start_hour": 9,
                "end_hour": 17,
            },
        )
        campaign, campaigns = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        await campaigns.add_recipient(campaign, phone_number="+447700900123")
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW.replace(hour=20))

        assert results["skipped"] == 1
        assert results["contacted"] == 0
        assert results["recipients"][0]["reason"] == ("after allowed calling hours (17:00)")
        assert provider.requests == []
        assert await voice_calls_for(db_session, biz_a.id) == []

    async def test_quiet_period_skips(self, db_session, biz_a):
        await make_config(
            db_session,
            biz_a.id,
            quiet_periods=[{"start": "01-01", "end": "12-31"}],
        )
        campaign, campaigns = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        await campaigns.add_recipient(campaign, phone_number="+447700900123")
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["skipped"] == 1
        assert results["recipients"][0]["reason"] == "within quiet period"
        assert provider.requests == []

    async def test_timezone_window_contacts(self, db_session, biz_a):
        """08:00 UTC in June is 09:00 Europe/London — just inside 9-17."""
        await make_config(
            db_session,
            biz_a.id,
            timezone="Europe/London",
            allowed_calling_hours={
                "days": [0, 1, 2, 3, 4, 5, 6],
                "start_hour": 9,
                "end_hour": 17,
            },
        )
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, with_preference=False)
        campaign, campaigns = await make_campaign(
            db_session,
            biz_a,
            purpose=CallPurpose.BOOKING_REMINDER.value,
            brain_version_id=version.id,
        )
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW.replace(hour=8))

        assert results["contacted"] == 1
        assert recipient.status == CampaignRecipientStatus.CONTACTED.value


# ── 3. Closed-world policy gating ──


class TestPolicyGating:
    async def test_dnc_customer_suppressed(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, opt_in=False, do_not_contact=True)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["suppressed"] == 1
        assert results["contacted"] == 0
        assert recipient.status == CampaignRecipientStatus.SUPPRESSED.value
        assert provider.requests == []

        events = await campaign_audit_events(db_session, biz_a.id)
        suppressed = [e for e in events if e.event_type == AuditEventType.CAMPAIGN_RECIPIENT_SUPPRESSED.value]
        assert len(suppressed) == 1
        assert suppressed[0].customer_id == customer.id
        assert suppressed[0].decision_evidence["decision"] == "DENY"

    async def test_missing_consent_skips_closed_world(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, with_preference=False)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["skipped"] == 1
        assert recipient.status == CampaignRecipientStatus.SKIPPED.value
        assert "consent" in results["recipients"][0]["reason"].lower()
        assert provider.requests == []

    async def test_missing_channel_config_skips(self, db_session, biz_a):
        """Closed-world: no VOICE channel config → REQUIRE_APPROVAL → SKIPPED."""
        await make_config(db_session, biz_a.id)
        campaign, campaigns = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123")
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["skipped"] == 1
        assert recipient.status == CampaignRecipientStatus.SKIPPED.value
        assert "VOICE" in results["recipients"][0]["reason"]
        assert provider.requests == []


# ── 4. Frequency limits ──


class TestFrequencyLimits:
    async def test_attempt_budget_exhausted_marks_failed(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)  # max_attempts = 3
        campaign, campaigns = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123")
        recipient.attempt_count = 3
        await db_session.flush()
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["failed"] == 1
        assert recipient.status == CampaignRecipientStatus.FAILED.value
        assert provider.requests == []
        assert await voice_calls_for(db_session, biz_a.id) == []

    async def test_per_campaign_limit_marks_failed(self, db_session, biz_a):
        await make_config(db_session, biz_a.id, customer_frequency_limits={"per_campaign": 1})
        campaign, campaigns = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123")
        recipient.attempt_count = 1
        await db_session.flush()
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["failed"] == 1
        assert recipient.status == CampaignRecipientStatus.FAILED.value

    async def test_daily_limit_skips(self, db_session, biz_a):
        await make_config(db_session, biz_a.id, max_daily_attempts=1)
        campaign, campaigns = await make_campaign(db_session, biz_a, purpose=CallPurpose.BOOKING_REMINDER.value)
        attempted = await campaigns.add_recipient(campaign, phone_number="+447700900111")
        attempted.status = CampaignRecipientStatus.CONTACTED.value
        attempted.attempt_count = 1
        attempted.last_attempt_at = NOW
        await db_session.flush()
        pending = await campaigns.add_recipient(campaign, phone_number="+447700900222")
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["skipped"] == 1
        assert pending.status == CampaignRecipientStatus.SKIPPED.value
        assert "daily attempt limit" in results["recipients"][0]["reason"]
        assert provider.requests == []


# ── 5. Processing ──


class TestProcessing:
    async def test_allowed_recipient_gets_call(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, opt_in=True)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["contacted"] == 1
        assert recipient.status == CampaignRecipientStatus.CONTACTED.value
        assert recipient.attempt_count == 1
        assert recipient.last_attempt_at is not None

        calls = await voice_calls_for(db_session, biz_a.id)
        assert len(calls) == 1
        call = calls[0]
        assert call.campaign_id == campaign.id
        assert call.brain_version_id == version.id
        assert call.customer_id == customer.id
        assert call.to_number == "+447700900123"
        assert call.purpose == CallPurpose.SERVICE_PROMOTION.value
        assert call.call_type == CallType.MARKETING.value
        assert call.idempotency_key == (f"campaign:{campaign.id}:{recipient.id}:1")
        assert call.provider_reference is not None
        assert call.status == CallStatus.INITIATING.value

        # Call provenance: campaign origin recorded as the request reason.
        call_events = await campaign_audit_events(db_session, biz_a.id, event_type_prefix="CALL_%")
        requested = [e for e in call_events if e.event_type == AuditEventType.CALL_REQUESTED.value]
        assert len(requested) == 1
        assert requested[0].decision_evidence["reason"] == "campaign"
        assert len(provider.requests) == 1

    async def test_rerun_does_not_duplicate_calls(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, opt_in=True)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        provider = StubVoiceProvider()
        execution = execution_for(db_session, provider)
        await execution.activate(campaign)
        await execution.process_campaign(campaign, now=NOW)

        second = await execution.process_campaign(campaign, now=NOW)

        assert second["processed"] == 0
        assert len(provider.requests) == 1
        assert len(await voice_calls_for(db_session, biz_a.id)) == 1

    async def test_transactional_campaign_bypasses_consent(self, db_session, biz_a):
        """Transactional purpose needs no consent preference (policy chain)."""
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, with_preference=False)
        campaign, campaigns = await make_campaign(
            db_session,
            biz_a,
            purpose=CallPurpose.BOOKING_REMINDER.value,
            brain_version_id=version.id,
        )
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["contacted"] == 1
        assert recipient.status == CampaignRecipientStatus.CONTACTED.value


# ── 6. Outcome settlement ──


class TestOutcomeSettlement:
    async def _campaign_with_contacted_recipient(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, opt_in=True)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        recipient = await campaigns.add_recipient(campaign, phone_number="+447700900123", customer_id=customer.id)
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)
        await execution.process_campaign(campaign, now=NOW)
        calls = await voice_calls_for(db_session, biz_a.id)
        return campaign, recipient, calls[0], execution

    async def test_completed_call_settles_recipient_and_campaign(self, db_session, biz_a):
        campaign, recipient, call, execution = await self._campaign_with_contacted_recipient(db_session, biz_a)
        call = await execution.orchestration.sync_provider_status(call, "ringing")
        call = await execution.orchestration.sync_provider_status(call, "in-progress")
        call = await execution.orchestration.sync_provider_status(call, "completed")

        settled = await execution.complete_campaign_recipient(call)

        assert settled is not None
        assert settled.status == CampaignRecipientStatus.COMPLETED.value
        assert settled.completed_at is not None
        assert campaign.status == CampaignStatus.COMPLETED.value

    async def test_failed_call_marks_recipient_failed(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer_a = await make_customer(db_session, biz_a, opt_in=True)
        customer_b = await make_customer(db_session, biz_a, opt_in=True)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900111", customer_id=customer_a.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900222", customer_id=customer_b.id)
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)
        await execution.process_campaign(campaign, now=NOW)
        calls = {c.to_number: c for c in await voice_calls_for(db_session, biz_a.id)}

        failed_call = await execution.orchestration.sync_provider_status(calls["+447700900111"], "no-answer")
        settled = await execution.complete_campaign_recipient(failed_call)

        assert settled.status == CampaignRecipientStatus.FAILED.value
        assert campaign.status == CampaignStatus.ACTIVE.value

    async def test_escalated_call_keeps_recipient_contacted(self, db_session, biz_a):
        campaign, recipient, call, execution = await self._campaign_with_contacted_recipient(db_session, biz_a)
        call = await execution.orchestration.sync_provider_status(call, "ringing")
        call = await execution.orchestration.sync_provider_status(call, "in-progress")
        await execution.lifecycle.escalate_call(call, escalation_reason="customer requested human")

        settled = await execution.complete_campaign_recipient(call)

        assert settled is not None
        assert settled.status == CampaignRecipientStatus.CONTACTED.value
        assert campaign.status == CampaignStatus.ACTIVE.value

    async def test_non_campaign_call_returns_none(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        lifecycle = VoiceCallLifecycleService(db_session)
        call = await lifecycle.request_call(
            business_id=biz_a.id,
            to_number="+447700900123",
            purpose=CallPurpose.BOOKING_REMINDER.value,
            provider=PROVIDER,
            idempotency_key=f"call-{uuid.uuid4().hex}",
        )
        execution = execution_for(db_session, StubVoiceProvider())

        assert await execution.complete_campaign_recipient(call) is None


# ── 7. Cancellation & audit provenance ──


class TestCancellationAndAudit:
    async def test_cancel_between_runs_leaves_pending_untouched(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        customer = await make_customer(db_session, biz_a, opt_in=True)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900111", customer_id=customer.id)
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)
        await execution.process_campaign(campaign, now=NOW)
        late = await campaigns.add_recipient(campaign, phone_number="+447700900222")

        await campaigns.transition_campaign(campaign, CampaignStatus.CANCELLED)
        with pytest.raises(StateTransitionError):
            await execution.process_campaign(campaign, now=NOW)

        assert late.status == CampaignRecipientStatus.PENDING.value
        assert len(await voice_calls_for(db_session, biz_a.id)) == 1

    async def test_campaign_audit_events_emitted(self, db_session, biz_a):
        await make_config(db_session, biz_a.id)
        version = await make_brain(db_session, biz_a)
        await setup_voice_policy(db_session, biz_a)
        allowed = await make_customer(db_session, biz_a, opt_in=True)
        dnc = await make_customer(db_session, biz_a, opt_in=False, do_not_contact=True)
        unknown = await make_customer(db_session, biz_a, with_preference=False)
        campaign, campaigns = await make_campaign(db_session, biz_a, brain_version_id=version.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900111", customer_id=allowed.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900222", customer_id=dnc.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900333", customer_id=unknown.id)
        execution = execution_for(db_session, StubVoiceProvider())
        await execution.activate(campaign)

        results = await execution.process_campaign(campaign, now=NOW)

        assert results["contacted"] == 1
        assert results["suppressed"] == 1
        assert results["skipped"] == 1

        events = await campaign_audit_events(db_session, biz_a.id)
        types = Counter(e.event_type for e in events)
        assert types[AuditEventType.CAMPAIGN_PROCESSING_STARTED.value] == 1
        assert types[AuditEventType.CAMPAIGN_RECIPIENT_SUPPRESSED.value] == 1
        assert types[AuditEventType.CAMPAIGN_RECIPIENT_SKIPPED.value] == 1
