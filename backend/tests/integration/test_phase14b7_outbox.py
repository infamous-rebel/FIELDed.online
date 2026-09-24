"""Phase 14B.2 Block F — voice outbox integration tests.

Covers (targeted per implementation block):
- Domain events emitted inside the same transaction as the state
  change:  voice.call_initiated (once — re-initiation never
  duplicates), voice.call_failed (terminal failures),
  voice.escalation_requested (human handoff), voice.campaign_completed
  (auto-completion)
- Outbox worker routing:  voice.* events → VoiceEventOrchestrator
  (idempotent in-app notifications only, never provider calls);
  everything else → the unchanged 14A orchestration service
- 14A coexistence:  a 14A event in the same batch is processed by
  OrchestrationService exactly as before
- Missing voice orchestrator:  voice events are never silently
  dropped (marked retryable, no notification)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.common import ProviderResult
from app.adapters.email.base import EmailMessage, EmailProvider
from app.adapters.push.stub import StubPushProvider
from app.adapters.sms.base import SMSMessage, SMSProvider
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.adapters.whatsapp.stub import StubWhatsAppProvider
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.common.enums import CallPurpose, CampaignStatus
from app.domain.communication.models import (
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    CustomerCommunicationPreference,
)
from app.domain.communication.orchestration import OrchestrationService
from app.domain.communication.repository import (
    CommunicationConfigRepository,
    ConsentRepository,
)
from app.domain.identity.models import Business, User
from app.domain.notification.models import Notification
from app.domain.outbox.models import OutboxEvent
from app.domain.outbox.repository import OutboxRepository
from app.domain.voice.campaign_execution import CampaignExecutionService
from app.domain.voice.campaign_service import CampaignService
from app.domain.voice.models import CommunicationCampaign, VoiceCall
from app.domain.voice.outbox_integration import (
    VoiceEventOrchestrator,
    emit_voice_event,
)
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.domain.voice.service import VoiceCallLifecycleService
from app.security.password import hash_password
from tests.factories import business_factory

PROVIDER = "stub"
NOW = datetime.now(UTC)


# ── Stubs ──


class StubVoiceProvider(VoiceProvider):
    """Deterministic in-memory voice provider (never network)."""

    def __init__(self) -> None:
        self.requests: list[VoiceCallRequest] = []

    @property
    def provider_name(self) -> str:
        return PROVIDER

    async def initiate_call(self, request: VoiceCallRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult.ok(f"CA{uuid.uuid4().hex[:24]}")


class FailingVoiceProvider(StubVoiceProvider):
    """A voice provider whose dial always fails."""

    def __init__(self, *, retryable: bool) -> None:
        super().__init__()
        self.retryable = retryable

    async def initiate_call(self, request: VoiceCallRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult.failure("provider unavailable", retryable=self.retryable)


class AssertingEmailProvider(EmailProvider):
    @property
    def provider_name(self) -> str:
        return "asserting"

    async def send(self, message: EmailMessage) -> ProviderResult:
        raise AssertionError("voice event processing must never call providers")


class AssertingSMSProvider(SMSProvider):
    @property
    def provider_name(self) -> str:
        return "asserting"

    async def send(self, message: SMSMessage) -> ProviderResult:
        raise AssertionError("voice event processing must never call providers")


# ── Setup helpers (same pattern as the other 14B blocks) ──


async def make_business(db_session: AsyncSession) -> Business:
    biz = business_factory(name="Voice Outbox Business")
    db_session.add(biz)
    await db_session.flush()
    return biz


async def make_config(db_session: AsyncSession, business_id: uuid.UUID) -> None:
    from app.domain.voice.models import CallAgentConfiguration

    db_session.add(
        CallAgentConfiguration(
            business_id=business_id,
            enabled=True,
            transactional_calling_enabled=True,
            marketing_calling_enabled=True,
            default_from_number="+441234567890",
            human_escalation_enabled=True,
        )
    )
    await db_session.flush()


async def make_brain(db_session: AsyncSession, biz: Business) -> BrainVersion:
    brain = BusinessBrain(business_id=biz.id)
    db_session.add(brain)
    await db_session.flush()
    version = BrainVersion(
        brain_id=brain.id,
        version_number=1,
        status="active",
        communication_config={},
    )
    db_session.add(version)
    await db_session.flush()
    brain.active_version_id = version.id
    await db_session.flush()
    return version


async def setup_voice_policy(db_session: AsyncSession, biz: Business) -> None:
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
    await db_session.flush()


async def make_customer(db_session: AsyncSession, biz: Business) -> User:
    user = User(
        email=f"cust-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    await ConsentRepository(db_session).upsert(
        CustomerCommunicationPreference(
            customer_id=user.id,
            business_id=biz.id,
            channel="VOICE",
            purpose="MARKETING",
            consent_state="OPTED_IN",
            opt_in=True,
            do_not_contact=False,
            source="test",
            consented_at=NOW,
        )
    )
    return user


async def make_campaign(
    db_session: AsyncSession, biz: Business, *, brain_version_id: uuid.UUID
) -> tuple[CommunicationCampaign, CampaignService]:
    campaigns = CampaignService(db_session)
    campaign = await campaigns.create_campaign(
        business_id=biz.id,
        name="Outbox campaign",
        channel="VOICE",
        purpose=CallPurpose.SERVICE_PROMOTION.value,
        brain_version_id=brain_version_id,
    )
    return campaign, campaigns


async def initiated_call(
    db_session: AsyncSession,
    biz: Business,
    provider: VoiceProvider,
    *,
    customer: User | None = None,
) -> VoiceCall:
    """Request → authorize → dial through the full domain stack."""
    lifecycle = VoiceCallLifecycleService(db_session)
    call = await lifecycle.request_call(
        business_id=biz.id,
        to_number="+447700900123",
        purpose=CallPurpose.BOOKING_REMINDER.value,
        provider=PROVIDER,
        idempotency_key=f"call-{uuid.uuid4().hex}",
        customer_id=customer.id if customer else None,
    )
    call = await lifecycle.authorize_call(call)
    orchestration = VoiceProviderOrchestrationService(db_session, provider)
    return await orchestration.initiate_call(call)


async def voice_outbox_events(
    db_session: AsyncSession,
    business_id: uuid.UUID,
    event_type: str | None = None,
) -> list[OutboxEvent]:
    stmt = select(OutboxEvent).where(
        OutboxEvent.business_id == business_id,
        OutboxEvent.event_type.like("voice.%"),
    )
    if event_type:
        stmt = stmt.where(OutboxEvent.event_type == event_type)
    result = await db_session.execute(stmt.order_by(OutboxEvent.created_at.asc()))
    return list(result.scalars().all())


async def notifications_for(db_session: AsyncSession, business_id: uuid.UUID) -> list[Notification]:
    result = await db_session.execute(select(Notification).where(Notification.business_id == business_id))
    return list(result.scalars().all())


def worker_orchestrator(db_session: AsyncSession) -> OrchestrationService:
    """A 14A orchestration service whose providers detect stray calls."""
    return OrchestrationService(
        db_session,
        email_provider=AssertingEmailProvider(),
        sms_provider=AssertingSMSProvider(),
        voice_provider=StubVoiceProvider(),
        whatsapp_provider=StubWhatsAppProvider(),
        push_provider=StubPushProvider(),
    )


# ── 1. Call lifecycle events ──


class TestCallEvents:
    async def test_initiation_emits_call_initiated_once(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        provider = StubVoiceProvider()

        call = await initiated_call(db_session, biz, provider)

        events = await voice_outbox_events(db_session, biz.id, "voice.call_initiated")
        assert len(events) == 1
        assert events[0].aggregate_type == "voice_call"
        assert events[0].aggregate_id == call.id
        assert events[0].payload["provider_reference"] == call.provider_reference
        assert events[0].status == "PENDING"

        # Idempotent re-initiation never dials or emits again.
        orchestration = VoiceProviderOrchestrationService(db_session, provider)
        await orchestration.initiate_call(call)
        assert len(provider.requests) == 1
        events = await voice_outbox_events(db_session, biz.id, "voice.call_initiated")
        assert len(events) == 1

    async def test_retryable_failure_keeps_call_initiating_without_event(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        provider = FailingVoiceProvider(retryable=True)

        call = await initiated_call(db_session, biz, provider)

        assert call.status == "INITIATING"
        assert await voice_outbox_events(db_session, biz.id) == []

    async def test_terminal_failure_emits_call_failed(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        provider = FailingVoiceProvider(retryable=False)

        call = await initiated_call(db_session, biz, provider)

        assert call.status == "FAILED"
        events = await voice_outbox_events(db_session, biz.id, "voice.call_failed")
        assert len(events) == 1
        assert events[0].aggregate_id == call.id
        assert events[0].payload["failure_code"] == "PROVIDER_ERROR"
        assert await voice_outbox_events(db_session, biz.id, "voice.call_initiated") == []


# ── 2. Escalation event ──


class TestEscalationEvent:
    async def test_escalation_emits_event(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        provider = StubVoiceProvider()

        call = await initiated_call(db_session, biz, provider)
        orchestration = VoiceProviderOrchestrationService(db_session, provider)
        call = await orchestration.sync_provider_status(call, "ringing")
        call = await orchestration.sync_provider_status(call, "in-progress")

        lifecycle = VoiceCallLifecycleService(db_session)
        escalation = await lifecycle.escalate_call(call, escalation_reason="customer requested human")

        events = await voice_outbox_events(db_session, biz.id, "voice.escalation_requested")
        assert len(events) == 1
        assert events[0].aggregate_type == "voice_call_escalation"
        assert events[0].aggregate_id == escalation.id
        assert events[0].payload["escalation_reason"] == "customer requested human"
        assert events[0].payload["call_id"] == str(call.id)


# ── 3. Campaign completion event ──


class TestCampaignEvent:
    async def test_campaign_completion_emits_event(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        version = await make_brain(db_session, biz)
        await setup_voice_policy(db_session, biz)
        customer = await make_customer(db_session, biz)
        campaign, campaigns = await make_campaign(db_session, biz, brain_version_id=version.id)
        await campaigns.add_recipient(campaign, phone_number="+447700900456", customer_id=customer.id)
        provider = StubVoiceProvider()
        execution = CampaignExecutionService(db_session, provider)
        await execution.activate(campaign)
        await execution.process_campaign(campaign, now=NOW)

        # No campaign-completion event while recipients are still open.
        assert campaign.status == CampaignStatus.ACTIVE.value
        assert await voice_outbox_events(db_session, biz.id, "voice.campaign_completed") == []

        # Settle the recipient through a completed call.
        calls = list((await db_session.execute(select(VoiceCall).where(VoiceCall.business_id == biz.id))).scalars())
        call = calls[0]
        call = await execution.orchestration.sync_provider_status(call, "ringing")
        call = await execution.orchestration.sync_provider_status(call, "in-progress")
        call = await execution.orchestration.sync_provider_status(call, "completed")
        settled = await execution.complete_campaign_recipient(call)

        assert settled is not None
        assert settled.status == "COMPLETED"
        assert campaign.status == CampaignStatus.COMPLETED.value
        events = await voice_outbox_events(db_session, biz.id, "voice.campaign_completed")
        assert len(events) == 1
        assert events[0].aggregate_type == "communication_campaign"
        assert events[0].aggregate_id == campaign.id
        assert events[0].payload["campaign_id"] == str(campaign.id)


# ── 4. Emission guard rails ──


class TestEmissionGuardRails:
    async def test_unknown_event_type_rejected(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        with pytest.raises(ValueError):
            await emit_voice_event(
                db_session,
                business_id=biz.id,
                event_type="voice.bogus",
                aggregate_type="voice_call",
                aggregate_id=uuid.uuid4(),
            )

    async def test_duplicate_emission_is_noop(self, db_session: AsyncSession):
        biz = await make_business(db_session)
        aggregate_id = uuid.uuid4()
        kwargs = {
            "business_id": biz.id,
            "event_type": "voice.call_completed",
            "aggregate_type": "voice_call",
            "aggregate_id": aggregate_id,
        }
        first = await emit_voice_event(db_session, **kwargs)
        second = await emit_voice_event(db_session, **kwargs)

        assert first is not None
        assert second is None
        assert len(await voice_outbox_events(db_session, biz.id)) == 1


# ── 5. Outbox worker routing ──


class TestWorkerVoiceRouting:
    async def test_voice_events_become_notifications_idempotently(self, db_session: AsyncSession):
        from app.workers import process_outbox_events

        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        provider = StubVoiceProvider()
        await initiated_call(db_session, biz, provider)

        events = await voice_outbox_events(db_session, biz.id)
        assert len(events) >= 1

        processed = await process_outbox_events(
            db_session,
            orchestrator=worker_orchestrator(db_session),
            voice_orchestrator=VoiceEventOrchestrator(db_session),
        )
        assert processed >= 1

        # Every voice event produced exactly one notification, keyed
        # notification:{outbox_event_id}, and no provider call was
        # made by event processing.
        notifications = await notifications_for(db_session, biz.id)
        assert len(notifications) == len(events)
        expected_keys = {f"notification:{e.id}" for e in events}
        assert {n.idempotency_key for n in notifications} == expected_keys
        # related_entity_id points at the aggregate (the call), not
        # the outbox row.
        aggregate_ids = {str(e.aggregate_id) for e in events}
        assert all(str(n.related_entity_id) in aggregate_ids for n in notifications)
        assert len(provider.requests) == 1

        refreshed = await voice_outbox_events(db_session, biz.id)
        assert all(e.status == "PROCESSED" for e in refreshed)

        # A second pass is a no-op — no duplicate notifications.
        processed_again = await process_outbox_events(
            db_session,
            orchestrator=worker_orchestrator(db_session),
            voice_orchestrator=VoiceEventOrchestrator(db_session),
        )
        assert processed_again == 0
        assert len(await notifications_for(db_session, biz.id)) == len(events)

    async def test_voice_events_without_voice_orchestrator_not_silently_dropped(self, db_session: AsyncSession):
        from app.workers import process_outbox_events

        biz = await make_business(db_session)
        await emit_voice_event(
            db_session,
            business_id=biz.id,
            event_type="voice.call_completed",
            aggregate_type="voice_call",
            aggregate_id=uuid.uuid4(),
            payload={"call_id": str(uuid.uuid4())},
        )

        processed = await process_outbox_events(
            db_session,
            orchestrator=worker_orchestrator(db_session),
        )
        assert processed == 0
        # The event was never processed and no notification exists.
        events = await voice_outbox_events(db_session, biz.id)
        assert len(events) == 1
        assert events[0].status in {"RETRYABLE", "FAILED"}
        assert await notifications_for(db_session, biz.id) == []

    async def test_14a_events_still_processed_in_same_batch(self, db_session: AsyncSession):
        from app.workers import process_outbox_events

        biz = await make_business(db_session)
        await make_config(db_session, biz.id)
        provider = StubVoiceProvider()
        call = await initiated_call(db_session, biz, provider)

        # A 14A-style event without communication_targets — the 14A
        # orchestration creates a notification only.
        quote_aggregate = uuid.uuid4()
        repo = OutboxRepository(db_session)
        await repo.create(
            OutboxEvent(
                business_id=biz.id,
                event_type="QUOTE_ISSUED",
                aggregate_type="quote",
                aggregate_id=quote_aggregate,
                payload={"quote_id": str(quote_aggregate)},
                idempotency_key=f"QUOTE_ISSUED:quote:{quote_aggregate}",
                status="PENDING",
                available_at=NOW,
            )
        )
        await db_session.flush()

        processed = await process_outbox_events(
            db_session,
            orchestrator=worker_orchestrator(db_session),
            voice_orchestrator=VoiceEventOrchestrator(db_session),
        )
        assert processed >= 2

        notifications = await notifications_for(db_session, biz.id)
        by_type = {n.notification_type: n for n in notifications}
        # The 14A event was handled by OrchestrationService as before…
        quote_notification = by_type["QUOTE_ISSUED"]
        assert quote_notification.related_entity_id == quote_aggregate
        # …and the voice event by the voice orchestrator.
        voice_notification = by_type["voice.call_initiated"]
        assert voice_notification.title == "Voice call initiated"
        assert voice_notification.related_entity_id == call.id
        # Neither path touched a provider.
        assert len(provider.requests) == 1
