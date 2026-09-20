"""Phase 14B.2 Block B — voice webhook processing tests.

Covers (targeted per implementation block):
- Signature verification: valid HMAC accepted; tampered payload,
  missing signature, and missing secret rejected (fail-closed);
  unsigned accepted only for the mock provider
- Idempotent event persistence (same external_event_id → duplicate,
  no double transition, no double audit)
- Provider state synchronization through webhook events (ringing,
  in-progress, completed two-step and from in-progress, terminal
  failures: no-answer / busy / failed / canceled, busy from INITIATING)
- No-op provider acknowledgments ("queued") noted on the attempt only
- Unknown provider statuses fail the webhook row (fail-closed)
- Webhook row linkage (voice_call_id, payload, PROCESSED status)
- Audit evidence contains provider event id + mapped status
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.domain.common.enums import AuditEventType, CallPurpose, CallStatus
from app.domain.communication.models import (
    CommunicationAuditEvent,
)
from app.domain.communication.repository import WebhookRepository
from app.domain.identity.models import Business, User
from app.domain.voice.models import CallAgentConfiguration, VoiceCall
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.domain.voice.repository import VoiceCallAttemptRepository
from app.domain.voice.service import VoiceCallLifecycleService
from app.domain.voice.webhook_service import (
    VoiceWebhookService,
    compose_voice_event_id,
    verify_webhook_signature,
)
from app.exceptions import DomainError
from app.security.password import hash_password
from tests.factories import business_factory, business_member_factory

WEBHOOK_PROVIDER = "twilio_voice"
SECRET = "whsec-test-123"
SIGNATURE_PAYLOAD = b'{"CallSid": "CAabc123", "CallStatus": "ringing"}'


# ── Stub provider ──


class StubVoiceProvider(VoiceProvider):
    """Deterministic in-memory voice provider (never network)."""

    def __init__(self, results: list[ProviderResult] | None = None) -> None:
        self.results = list(results or [])
        self.requests: list[VoiceCallRequest] = []

    @property
    def provider_name(self) -> str:
        return "stub"

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
    biz = business_factory(name="Webhook Business A")
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
    )
    defaults.update(overrides)
    config = CallAgentConfiguration(**defaults)
    db_session.add(config)
    await db_session.flush()
    return config


async def initiated_call(
    db_session: AsyncSession,
    biz: Business,
    *,
    purpose: str = CallPurpose.BOOKING_REMINDER,
) -> tuple[VoiceCall, VoiceCallLifecycleService, VoiceProviderOrchestrationService]:
    """Configured call dialed through the stub orchestration (INITIATING)."""
    await make_config(db_session, biz.id)
    lifecycle = VoiceCallLifecycleService(db_session)
    orchestration = VoiceProviderOrchestrationService(db_session, StubVoiceProvider())
    call = await lifecycle.request_call(
        business_id=biz.id,
        to_number="+447700900123",
        purpose=purpose,
        provider=WEBHOOK_PROVIDER,
        idempotency_key=f"call-{uuid.uuid4().hex}",
    )
    call = await lifecycle.authorize_call(call)
    call = await orchestration.initiate_call(call)
    return call, lifecycle, orchestration


def webhook_service_for(
    db_session: AsyncSession,
    orchestration: VoiceProviderOrchestrationService,
) -> VoiceWebhookService:
    return VoiceWebhookService(db_session, orchestration=orchestration)


async def process_status(
    db_session: AsyncSession,
    orchestration: VoiceProviderOrchestrationService,
    call: VoiceCall,
    status: str,
    *,
    event_id: str | None = None,
    call_arg: VoiceCall | None = None,
) -> dict:
    """Submit one provider status callback through the webhook service."""
    service = webhook_service_for(db_session, orchestration)
    reference = call.provider_reference
    return await service.process_event(
        provider=WEBHOOK_PROVIDER,
        external_event_id=event_id or compose_voice_event_id(reference, status),
        event_type=status,
        payload={"CallSid": reference, "CallStatus": status},
        call=call_arg,
    )


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


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


# ── 1. Signature verification ──


class TestSignatureVerification:
    def test_valid_signature_accepted(self):
        assert (
            verify_webhook_signature(
                WEBHOOK_PROVIDER,
                SIGNATURE_PAYLOAD,
                {"X-Voice-Signature": _sign(SIGNATURE_PAYLOAD, SECRET)},
                SECRET,
            )
            is True
        )

    def test_tampered_payload_rejected(self):
        tampered = SIGNATURE_PAYLOAD + b" "
        assert (
            verify_webhook_signature(
                WEBHOOK_PROVIDER,
                tampered,
                {"X-Voice-Signature": _sign(SIGNATURE_PAYLOAD, SECRET)},
                SECRET,
            )
            is False
        )

    def test_missing_signature_rejected(self):
        assert verify_webhook_signature(WEBHOOK_PROVIDER, SIGNATURE_PAYLOAD, {}, SECRET) is False

    def test_wrong_secret_rejected(self):
        assert (
            verify_webhook_signature(
                WEBHOOK_PROVIDER,
                SIGNATURE_PAYLOAD,
                {"X-Voice-Signature": _sign(SIGNATURE_PAYLOAD, "whsec-other")},
                SECRET,
            )
            is False
        )

    def test_missing_secret_fails_closed(self):
        assert (
            verify_webhook_signature(
                WEBHOOK_PROVIDER,
                SIGNATURE_PAYLOAD,
                {"X-Voice-Signature": _sign(SIGNATURE_PAYLOAD, SECRET)},
                None,
            )
            is False
        )

    def test_mock_provider_unsigned_allowed(self):
        assert verify_webhook_signature("mock", SIGNATURE_PAYLOAD, {}, None) is True

    def test_twilio_signature_header_accepted(self):
        assert (
            verify_webhook_signature(
                WEBHOOK_PROVIDER,
                SIGNATURE_PAYLOAD,
                {"X-Twilio-Signature": _sign(SIGNATURE_PAYLOAD, SECRET)},
                SECRET,
            )
            is True
        )

    def test_case_insensitive_header_and_uppercase_hex(self):
        assert (
            verify_webhook_signature(
                WEBHOOK_PROVIDER,
                SIGNATURE_PAYLOAD,
                {"x-voice-signature": _sign(SIGNATURE_PAYLOAD, SECRET).upper()},
                SECRET,
            )
            is True
        )


# ── 2. State synchronization through webhook events ──


class TestWebhookStateSync:
    async def test_ringing_event_transitions_call(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)

        result = await process_status(db_session, orchestration, call, "ringing")

        assert result["status"] == "accepted"
        assert call.status == CallStatus.RINGING.value

        webhook = await WebhookRepository(db_session).get_by_provider_event(
            WEBHOOK_PROVIDER, compose_voice_event_id(call.provider_reference, "ringing")
        )
        assert webhook is not None
        assert webhook.processing_status == "PROCESSED"
        assert webhook.processed_at is not None
        assert webhook.voice_call_id == call.id
        assert webhook.raw_payload["CallSid"] == call.provider_reference

    async def test_in_progress_event_connects_call(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)
        await process_status(db_session, orchestration, call, "ringing")

        await process_status(db_session, orchestration, call, "in-progress")

        assert call.status == CallStatus.CONNECTED.value

    async def test_completed_from_in_progress_ends_session(self, db_session, biz_a):
        call, lifecycle, orchestration = await initiated_call(db_session, biz_a)
        await process_status(db_session, orchestration, call, "ringing")
        await process_status(db_session, orchestration, call, "in-progress")
        session_row = await lifecycle.start_session(call)

        await process_status(db_session, orchestration, call, "completed")

        assert call.status == CallStatus.COMPLETED.value
        assert session_row.session_status == "COMPLETED"
        assert session_row.ended_at is not None

    async def test_completed_from_ringing_is_two_step(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)
        await process_status(db_session, orchestration, call, "ringing")

        await process_status(db_session, orchestration, call, "completed")

        assert call.status == CallStatus.COMPLETED.value
        assert call.connected_at is not None
        assert call.completed_at is not None

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("no-answer", CallStatus.NO_ANSWER),
            ("busy", CallStatus.BUSY),
            ("failed", CallStatus.FAILED),
            ("canceled", CallStatus.CANCELLED),
        ],
    )
    async def test_terminal_failures_from_ringing(self, db_session, biz_a, status, expected):
        call, _, orchestration = await initiated_call(db_session, biz_a)
        await process_status(db_session, orchestration, call, "ringing")

        await process_status(db_session, orchestration, call, status)

        assert call.status == expected.value

    async def test_busy_from_initiating_fails_call(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)

        await process_status(db_session, orchestration, call, "busy")

        # Deterministic pre-step: busy is unreachable from INITIATING.
        assert call.status == CallStatus.FAILED.value
        assert call.failure_code == CallStatus.BUSY.value

    async def test_queued_event_is_noop_on_call(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)

        result = await process_status(db_session, orchestration, call, "queued")

        assert result["status"] == "accepted"
        assert call.status == CallStatus.INITIATING.value
        attempts = await VoiceCallAttemptRepository(db_session).list_for_call(call.id)
        assert attempts[-1].status == "QUEUED"
        # No significant-event audit: initiation outcome only.
        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_PROVIDER_STATE_SYNC.value] == 1

    async def test_unknown_status_fails_webhook_row(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)
        event_id = compose_voice_event_id(call.provider_reference, "smoke-signals")
        service = webhook_service_for(db_session, orchestration)

        with pytest.raises(DomainError, match="Unknown provider call status"):
            await service.process_event(
                provider=WEBHOOK_PROVIDER,
                external_event_id=event_id,
                event_type="smoke-signals",
                payload={"CallSid": call.provider_reference},
            )

        webhook = await WebhookRepository(db_session).get_by_provider_event(
            WEBHOOK_PROVIDER, event_id
        )
        assert webhook.processing_status == "FAILED"
        assert "Unknown provider call status" in webhook.error_metadata["error"]
        assert call.status == CallStatus.INITIATING.value

    async def test_explicit_call_argument_is_used(self, db_session, biz_a):
        """A pre-resolved call bypasses reference lookup."""
        call, _, orchestration = await initiated_call(db_session, biz_a)
        service = webhook_service_for(db_session, orchestration)

        result = await service.process_event(
            provider=WEBHOOK_PROVIDER,
            external_event_id=f"evt-{uuid.uuid4().hex}",
            event_type="ringing",
            payload={"CallStatus": "ringing"},
            call=call,
        )

        assert result["status"] == "accepted"
        assert result["call_id"] == str(call.id)
        assert call.status == CallStatus.RINGING.value


# ── 3. Idempotency ──


class TestWebhookIdempotency:
    async def test_duplicate_event_not_processed_twice(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)
        first = await process_status(db_session, orchestration, call, "ringing")
        assert call.status == CallStatus.RINGING.value

        second = await process_status(db_session, orchestration, call, "ringing")

        assert first["status"] == "accepted"
        assert second["status"] == "duplicate"
        assert second["webhook_id"] == first["webhook_id"]
        assert call.status == CallStatus.RINGING.value

        rows = await WebhookRepository(db_session).get_by_provider_event(
            WEBHOOK_PROVIDER, compose_voice_event_id(call.provider_reference, "ringing")
        )
        assert str(rows.id) == first["webhook_id"]

        # One sync audit only (plus the initiation-outcome audit).
        types = Counter(e.event_type for e in await call_audit_events(db_session, biz_a.id))
        assert types[AuditEventType.CALL_PROVIDER_STATE_SYNC.value] == 2

    async def test_distinct_statuses_are_distinct_events(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)

        await process_status(db_session, orchestration, call, "ringing")
        await process_status(db_session, orchestration, call, "in-progress")

        # Both processed (not collapsed by idempotency) and the call
        # reflects the latest state.
        assert call.status == CallStatus.CONNECTED.value
        webhook_repo = WebhookRepository(db_session)
        ringing = await webhook_repo.get_by_provider_event(
            WEBHOOK_PROVIDER, compose_voice_event_id(call.provider_reference, "ringing")
        )
        in_progress = await webhook_repo.get_by_provider_event(
            WEBHOOK_PROVIDER,
            compose_voice_event_id(call.provider_reference, "in-progress"),
        )
        assert ringing is not None and in_progress is not None
        assert ringing.id != in_progress.id


# ── 4. Audit evidence ──


class TestWebhookAuditEvidence:
    async def test_audit_contains_event_id_and_mapped_status(self, db_session, biz_a):
        call, _, orchestration = await initiated_call(db_session, biz_a)
        event_id = compose_voice_event_id(call.provider_reference, "ringing")

        await process_status(db_session, orchestration, call, "ringing")

        sync_events = [
            e
            for e in await call_audit_events(db_session, biz_a.id)
            if e.event_type == AuditEventType.CALL_PROVIDER_STATE_SYNC.value
        ]
        webhook_syncs = [e for e in sync_events if e.metadata_.get("provider_event_id") == event_id]
        assert len(webhook_syncs) == 1
        evidence = webhook_syncs[0].metadata_
        assert evidence["mapped_status"] == CallStatus.RINGING.value
        assert evidence["previous_status"] == CallStatus.INITIATING.value
        assert evidence["provider"] == WEBHOOK_PROVIDER
        assert evidence["call_id"] == str(call.id)
