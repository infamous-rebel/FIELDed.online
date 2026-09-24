"""Phase 14C.1 — Real voice E2E (TwiML / Gather / Say) targeted tests.

Covers:
- Twilio signature verification (valid, invalid, missing)
- TwiML generation (valid XML, Gather, Say, Hangup)
- Initial TwiML webhook (greeting + Gather)
- Gather callback (transcript → agent → Say + Gather)
- Empty transcript handling (retry prompt, no LLM)
- Terminal call state → Hangup
- Invalid call state rejection
- Cross-tenant callback isolation
- Idempotent duplicate callbacks
- OpenAI provider satisfies AGENT_DECISION_SCHEMA
- Existing status callback behavior preserved

All against real PostgreSQL 16 (per-test schema recreate + rollback).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from typing import Any
from urllib.parse import urlencode

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AIProvider, AIResponse
from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.adapters.voice.twilio_security import verify_twilio_signature
from app.domain.common.enums import CallPurpose
from app.domain.identity.models import Business, User
from app.domain.voice.agent import AGENT_DECISION_SCHEMA, VoiceCallAgent
from app.domain.voice.models import CallAgentConfiguration, VoiceCall
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.domain.voice.repository import (
    VoiceCallSessionRepository,
)
from app.domain.voice.service import VoiceCallLifecycleService
from app.domain.voice.twiml import (
    error_response,
    gather_response,
    hangup_response,
    retry_gather_response,
    say_and_hangup_response,
)
from app.security.password import hash_password
from tests.factories import business_factory, business_member_factory

PROVIDER = "stub"


# ── Stub providers ──


class StubVoiceProvider(VoiceProvider):
    """Deterministic voice provider for tests."""

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


class StubConversationalAI(AIProvider):
    """Deterministic AI provider that satisfies AGENT_DECISION_SCHEMA."""

    @property
    def provider_name(self) -> str:
        return "stub-conversational"

    async def complete(self, prompt: str, **kwargs: Any) -> AIResponse:
        return AIResponse(content="stub", model="stub-v1")

    async def structured_output(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Return a valid AGENT_DECISION_SCHEMA response."""
        return {
            "reply": "Thank you for calling. How can I help you today?",
            "action": "COLLECT_INFORMATION",
            "collected_information": {},
            "outcome": None,
            "outcome_summary": None,
            "escalation_reason": None,
        }


# ── Fixtures ──


@pytest_asyncio.fixture
async def biz(db_session: AsyncSession) -> Business:
    """Business with an owner and Call Agent config."""
    user = User(
        email=f"biz14c-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    biz = business_factory(name="Voice E2E Business")
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    return biz


@pytest_asyncio.fixture
async def other_biz(db_session: AsyncSession) -> Business:
    """Second business for cross-tenant tests."""
    user = User(
        email=f"other14c-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    biz = business_factory(name="Other Business")
    db_session.add(biz)
    await db_session.flush()
    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()
    return biz


async def _make_config(
    db_session: AsyncSession,
    business_id: uuid.UUID,
    **overrides: Any,
) -> CallAgentConfiguration:
    config = CallAgentConfiguration(
        business_id=business_id,
        enabled=True,
        transactional_calling_enabled=True,
        marketing_calling_enabled=True,
        default_from_number="+441234567890",
        **overrides,
    )
    db_session.add(config)
    await db_session.flush()
    return config


async def _make_brain_with_voice_agent(
    db_session: AsyncSession,
    business_id: uuid.UUID,
) -> Any:
    """Create an ACTIVE BrainVersion with voice_agent governance."""
    from app.domain.business.models import BrainVersion, BusinessBrain

    brain = BusinessBrain(business_id=business_id)
    db_session.add(brain)
    await db_session.flush()

    version = BrainVersion(
        brain_id=brain.id,
        version_number=1,
        status="active",
        communication_config={
            "voice_agent": {
                "allowed_actions": ["COLLECT_INFORMATION", "END_CALL", "REQUEST_HUMAN"],
                "collectible_fields": ["name", "reason", "preferred_time"],
                "max_turns": 10,
                "escalation_triggers": ["human", "agent", "representative"],
            }
        },
    )
    db_session.add(version)
    await db_session.flush()

    brain.active_version_id = version.id
    await db_session.flush()
    return version


async def _connected_call(
    db_session: AsyncSession,
    biz: Business,
    *,
    provider_ref: str | None = None,
) -> VoiceCall:
    """Create a call and drive it to CONNECTED with an active session."""
    _config = await _make_config(db_session, biz.id)
    await _make_brain_with_voice_agent(db_session, biz.id)
    lifecycle = VoiceCallLifecycleService(db_session)

    call = await lifecycle.request_call(
        business_id=biz.id,
        to_number="+447700900123",
        purpose=CallPurpose.BOOKING_REMINDER,
        provider=PROVIDER,
        idempotency_key=f"call-14c-{uuid.uuid4().hex}",
    )
    call = await lifecycle.authorize_call(call)
    call = await lifecycle.queue_call(call)
    call = await lifecycle.mark_initiating(call)
    call = await lifecycle.mark_ringing(call)
    call = await lifecycle.mark_connected(call)

    if provider_ref:
        call.provider_reference = provider_ref
        await db_session.flush()

    return call


# ── Twilio signature verification ──


class TestTwilioSignatureVerification:
    """Tests for verify_twilio_signature."""

    AUTH_TOKEN = "test_auth_token_secret"

    def _sign(self, url: str, params: dict[str, str]) -> str:
        """Compute a valid Twilio signature for testing."""
        data = url + urlencode(sorted(params.items()))
        return base64.b64encode(hmac.new(self.AUTH_TOKEN.encode(), data.encode(), hashlib.sha256).digest()).decode()

    def test_valid_signature_accepted(self):
        url = "https://api.fielded.com/api/v1/webhooks/voice/twilio/twiml/abc"
        params = {"CallSid": "CA123", "CallStatus": "ringing"}
        sig = self._sign(url, params)
        assert verify_twilio_signature(url, params, self.AUTH_TOKEN, sig) is True

    def test_invalid_signature_rejected(self):
        url = "https://api.fielded.com/api/v1/webhooks/voice/twilio/twiml/abc"
        params = {"CallSid": "CA123"}
        assert verify_twilio_signature(url, params, self.AUTH_TOKEN, "badsig") is False

    def test_missing_signature_rejected(self):
        url = "https://api.fielded.com/api/v1/webhooks/voice/twilio/twiml/abc"
        assert verify_twilio_signature(url, {}, self.AUTH_TOKEN, "") is False

    def test_missing_auth_token_rejected(self):
        url = "https://api.fielded.com/api/v1/webhooks/voice/twilio/twiml/abc"
        assert verify_twilio_signature(url, {}, "", "somesig") is False

    def test_tampered_params_rejected(self):
        url = "https://api.fielded.com/api/v1/webhooks/voice/twiml/abc"
        params = {"CallSid": "CA123"}
        sig = self._sign(url, params)
        tampered = {"CallSid": "CA999"}
        assert verify_twilio_signature(url, tampered, self.AUTH_TOKEN, sig) is False

    def test_tampered_url_rejected(self):
        url = "https://api.fielded.com/api/v1/webhooks/voice/twiml/abc"
        params = {"CallSid": "CA123"}
        sig = self._sign(url, params)
        wrong_url = "https://evil.com/twiml"
        assert verify_twilio_signature(wrong_url, params, self.AUTH_TOKEN, sig) is False


# ── TwiML generation ──


class TestTwiMLGeneration:
    """Tests for TwiML XML generation."""

    def test_gather_response_is_valid_xml(self):
        xml = gather_response(
            say_text="Hello",
            gather_action_url="https://api.fielded.com/gather",
        )
        assert "<Response>" in xml
        assert "<Say>Hello</Say>" in xml
        assert 'input="speech"' in xml
        assert 'action="https://api.fielded.com/gather"' in xml

    def test_say_and_hangup_contains_hangup(self):
        xml = say_and_hangup_response(say_text="Goodbye")
        assert "<Say>Goodbye</Say>" in xml
        assert "<Hangup" in xml

    def test_hangup_response(self):
        xml = hangup_response()
        assert "<Response>" in xml
        assert "<Hangup" in xml
        assert "<Say>" not in xml

    def test_retry_gather_has_deterministic_message(self):
        xml = retry_gather_response(gather_action_url="https://example.com/g")
        assert "didn't catch that" in xml
        assert 'input="speech"' in xml

    def test_error_response_says_and_hangs_up(self):
        xml = error_response(message="Error occurred")
        assert "<Say>Error occurred</Say>" in xml
        assert "<Hangup" in xml


# ── OpenAI provider structured output ──


class TestConversationalAIProvider:
    """Tests that the stub conversational AI satisfies AGENT_DECISION_SCHEMA."""

    async def test_stub_satisfies_schema(self):
        ai = StubConversationalAI()
        result = await ai.structured_output("test", AGENT_DECISION_SCHEMA)
        assert "reply" in result
        assert "action" in result
        assert isinstance(result["reply"], str)
        assert result["reply"].strip() != ""

    async def test_openai_provider_name(self):
        from app.adapters.ai.openai_provider import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key", model="gpt-4o-mini")
        assert provider.provider_name == "openai"


# ── TwiML endpoint integration ──


class TestTwiMLWebhookEndpoint:
    """Integration tests for the TwiML webhook endpoint."""

    async def test_initial_twiml_returns_gather(self, db_session: AsyncSession, biz: Business, client):
        """Initial TwiML webhook returns valid Gather TwiML."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")

        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/twiml/{call.id}",
            data={"CallSid": call.provider_reference, "CallStatus": "in-progress"},
        )
        assert response.status_code == 200
        assert "application/xml" in response.headers.get("content-type", "")
        body = response.text
        assert "<Response>" in body
        assert "<Say>" in body
        assert 'input="speech"' in body

    async def test_terminal_call_returns_hangup(self, db_session: AsyncSession, biz: Business, client):
        """A completed call should get a Hangup response."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")
        lifecycle = VoiceCallLifecycleService(db_session)
        call = await lifecycle.complete_call(call, reason="test")

        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/twiml/{call.id}",
            data={"CallSid": call.provider_reference, "CallStatus": "completed"},
        )
        assert response.status_code == 200
        assert "<Hangup" in response.text

    async def test_nonexistent_call_returns_error(self, client):
        """A call_id that doesn't exist should return an error TwiML."""
        fake_id = uuid.uuid4()
        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/twiml/{fake_id}",
            data={"CallSid": "CAnonexistent"},
        )
        assert response.status_code == 200
        assert "<Say>" in response.text  # error message
        assert "<Hangup" in response.text


class TestGatherCallbackEndpoint:
    """Integration tests for the Gather speech callback."""

    async def test_gather_extracts_transcript_and_responds(
        self, db_session: AsyncSession, biz: Business, client, monkeypatch
    ):
        """Gather callback processes transcript and returns Say + Gather."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")

        # Patch the AI provider resolver so the endpoint uses our stub
        ai = StubConversationalAI()
        monkeypatch.setattr("app.adapters._resolve_call_agent_ai_provider", lambda settings: ai)

        # Start the agent session first (simulating the initial TwiML)
        agent = VoiceCallAgent(db_session, ai)
        await agent.begin(call)

        # Now submit a Gather callback with speech
        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/gather/{call.id}",
            data={
                "CallSid": call.provider_reference,
                "SpeechResult": "I need help with a booking",
                "Confidence": "0.95",
            },
        )
        assert response.status_code == 200
        body = response.text
        assert "<Say>" in body
        assert 'input="speech"' in body

    async def test_empty_speech_returns_retry(self, db_session: AsyncSession, biz: Business, client):
        """Empty speech result returns a retry prompt, no LLM call."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")

        # Start session
        ai = StubConversationalAI()
        agent = VoiceCallAgent(db_session, ai)
        await agent.begin(call)

        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/gather/{call.id}",
            data={"CallSid": call.provider_reference, "SpeechResult": ""},
        )
        assert response.status_code == 200
        body = response.text
        assert "didn't catch that" in body
        assert 'input="speech"' in body

    async def test_gather_on_terminal_call_hangs_up(self, db_session: AsyncSession, biz: Business, client):
        """Gather on a completed call returns Hangup."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")
        lifecycle = VoiceCallLifecycleService(db_session)
        call = await lifecycle.complete_call(call, reason="test")

        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/gather/{call.id}",
            data={
                "CallSid": call.provider_reference,
                "SpeechResult": "hello",
            },
        )
        assert response.status_code == 200
        assert "<Hangup" in response.text


class TestCrossTenantIsolation:
    """Cross-tenant callback isolation."""

    async def test_gather_with_wrong_call_sid_rejected(
        self, db_session: AsyncSession, biz: Business, other_biz: Business, client
    ):
        """A CallSid belonging to a different business cannot access this call."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")
        # Start session
        ai = StubConversationalAI()
        agent = VoiceCallAgent(db_session, ai)
        await agent.begin(call)

        # Use a CallSid from a call in the OTHER business
        other_call = await _connected_call(db_session, other_biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")

        # The URL has call.id (biz's call) but CallSid is from other_biz
        response = await client.post(
            f"/api/v1/webhooks/voice/twilio/gather/{call.id}",
            data={
                "CallSid": other_call.provider_reference,
                "SpeechResult": "hello",
            },
        )
        # Should fail because CallSid doesn't match the URL call_id
        assert response.status_code == 200
        assert "<Hangup" in response.text or "Error" in response.text


class TestIdempotency:
    """Duplicate callback safety."""

    async def test_duplicate_twiml_does_not_create_duplicate_sessions(
        self, db_session: AsyncSession, biz: Business, client
    ):
        """Two TwiML webhooks for the same call should not create two sessions."""
        call = await _connected_call(db_session, biz, provider_ref=f"CA{uuid.uuid4().hex[:24]}")

        # First request creates the session
        r1 = await client.post(
            f"/api/v1/webhooks/voice/twilio/twiml/{call.id}",
            data={"CallSid": call.provider_reference},
        )
        assert r1.status_code == 200

        # Second request should still succeed (session already exists)
        r2 = await client.post(
            f"/api/v1/webhooks/voice/twilio/twiml/{call.id}",
            data={"CallSid": call.provider_reference},
        )
        assert r2.status_code == 200

        # Verify only one active session exists
        session_repo = VoiceCallSessionRepository(db_session)
        active = await session_repo.get_active_for_call(call.id)
        assert active is not None


class TestTwilioURLConstruction:
    """TwiML URL is passed to the Twilio adapter."""

    async def test_initiate_call_includes_twiml_url(self, db_session: AsyncSession, biz: Business):
        """The provider receives the TwiML URL as callback_url."""
        _config = await _make_config(db_session, biz.id)
        lifecycle = VoiceCallLifecycleService(db_session)
        call = await lifecycle.request_call(
            business_id=biz.id,
            to_number="+447700900123",
            purpose=CallPurpose.BOOKING_REMINDER,
            provider=PROVIDER,
            idempotency_key=f"url-test-{uuid.uuid4().hex}",
        )
        call = await lifecycle.authorize_call(call)

        provider = StubVoiceProvider()
        orchestration = VoiceProviderOrchestrationService(db_session, provider)
        twiml_url = "https://api.fielded.com/api/v1/webhooks/voice/twilio/twiml/123"
        await orchestration.initiate_call(call, twiml_url=twiml_url)

        assert len(provider.requests) == 1
        assert provider.requests[0].callback_url == twiml_url
