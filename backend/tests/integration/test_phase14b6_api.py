"""Phase 14B.2 Block E — voice API layer tests.

Covers (targeted per implementation block):
- API authorization matrix: unauthenticated → 401; cross-tenant
  member → 403; staff vs admin role gates
- Agent config upsert (ADMIN+) with write-only webhook secret
- Call request + initiation (stub provider), idempotency, list/get,
  cancel
- Governed agent turn over the API (scripted AI proposal)
- Deterministic outcome recording
- Escalation lifecycle over the API (create/assign/accept/resolve)
  with cross-business assignment rejection
- Campaign endpoints: create/transition (governed activation)/
  recipients/execute
- Voice webhook endpoint: HMAC signature enforcement, state sync,
  idempotent duplicate handling, mock-provider exemption
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AIProvider
from app.adapters.common import ProviderResult
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.communication.models import (
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    CustomerCommunicationPreference,
)
from app.domain.communication.repository import (
    CommunicationConfigRepository,
    ConsentRepository,
)
from app.domain.identity.models import Business, BusinessMember, User
from app.domain.voice.agent import VoiceCallAgent
from app.domain.voice.models import CallAgentConfiguration, VoiceCall
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.security.password import hash_password
from tests.factories import business_factory, business_member_factory

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


class ScriptedAI(AIProvider):
    """Deterministic AI provider returning queued agent proposals."""

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = list(responses or [])

    @property
    def provider_name(self) -> str:
        return "stub"

    async def complete(self, prompt, *, system=None, max_tokens=4096, temperature=0.7):
        raise AssertionError("complete() is not used by the Call Agent")

    async def structured_output(self, prompt, schema, *, system=None, max_tokens=4096):
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


@pytest.fixture
def stub_providers(monkeypatch: pytest.MonkeyPatch) -> StubVoiceProvider:
    """Inject deterministic voice + AI providers into the API seams."""
    provider = StubVoiceProvider()
    import app.adapters as adapters_module
    from app.adapters import ProviderFactory

    monkeypatch.setattr(
        ProviderFactory,
        "from_settings",
        classmethod(lambda cls, settings: SimpleNamespace(voice_provider=provider)),
    )
    monkeypatch.setattr(adapters_module, "_resolve_call_agent_ai_provider", lambda settings: ScriptedAI())
    return provider


# ── Fixtures ──


async def _make_user(db_session: AsyncSession, label: str) -> User:
    user = User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def voice_env(db_session: AsyncSession, client: AsyncClient) -> dict:
    """Business A (owner + staff) and Business B (owner) with logins."""
    owner = await _make_user(db_session, "owner")
    staff = await _make_user(db_session, "staff")
    other = await _make_user(db_session, "other")

    biz_a = business_factory(name="Voice API Business A")
    db_session.add(biz_a)
    await db_session.flush()
    biz_b = business_factory(name="Voice API Business B")
    db_session.add(biz_b)
    await db_session.flush()

    db_session.add_all(
        [
            business_member_factory(user_id=owner.id, business_id=biz_a.id, role="owner"),
            business_member_factory(user_id=staff.id, business_id=biz_a.id, role="staff"),
            business_member_factory(user_id=other.id, business_id=biz_b.id, role="owner"),
        ]
    )
    await db_session.flush()
    member_rows = (
        await db_session.execute(
            BusinessMember.__table__.select().where(
                BusinessMember.user_id.in_([staff.id, other.id])
            )
        )
    ).all()
    member_ids = {row.user_id: row.id for row in member_rows}

    async def login(user: User) -> dict[str, str]:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "testpassword123"},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return {
        "biz_a": biz_a,
        "biz_b": biz_b,
        "owner": owner,
        "staff": staff,
        "other": other,
        "owner_headers": await login(owner),
        "staff_headers": await login(staff),
        "other_headers": await login(other),
        "staff_member_id": member_ids[staff.id],
        "other_member_id": member_ids[other.id],
    }


# ── Domain-level setup helpers (shared session with the app) ──


async def make_config(db_session: AsyncSession, business_id: uuid.UUID) -> None:
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


async def make_customer(
    db_session: AsyncSession,
    biz: Business,
    *,
    opt_in: bool = True,
) -> User:
    """A customer user with a VOICE/MARKETING consent preference."""
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
            consent_state="OPTED_IN" if opt_in else "UNKNOWN",
            opt_in=opt_in,
            do_not_contact=False,
            source="test",
            consented_at=NOW if opt_in else None,
        )
    )
    return user


async def make_brain(
    db_session: AsyncSession, biz: Business, *, voice_agent: dict | None = None
) -> BrainVersion:
    brain = BusinessBrain(business_id=biz.id)
    db_session.add(brain)
    await db_session.flush()
    version = BrainVersion(
        brain_id=brain.id,
        version_number=1,
        status="active",
        communication_config=({"voice_agent": voice_agent} if voice_agent else {}),
    )
    db_session.add(version)
    await db_session.flush()
    brain.active_version_id = version.id
    await db_session.flush()
    return version


VOICE_AGENT_CONFIG = {
    "max_turns": 3,
    "collectible_fields": ["callback_number", "preferred_time"],
    "allowed_actions": ["CONTINUE", "COLLECT_INFORMATION", "REQUEST_HUMAN", "END_CALL"],
    "escalation_triggers": ["customer requests human"],
}


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
    await repo.upsert_purpose_config(
        BusinessCommunicationPurpose(
            business_id=biz.id,
            purpose="TRANSACTIONAL",
            enabled=True,
            permitted_channels=["VOICE"],
        )
    )
    await db_session.flush()


# ── 1. Authorization matrix ──


class TestAuthMatrix:
    async def test_endpoints_require_auth(self, client: AsyncClient, voice_env):
        biz_id = voice_env["biz_a"].id
        assert (await client.get(f"/api/v1/{biz_id}/voice/calls")).status_code == 401
        assert (await client.post(f"/api/v1/{biz_id}/voice/calls", json={})).status_code == 401
        assert (await client.get(f"/api/v1/{biz_id}/voice/agent-config")).status_code == 401
        assert (await client.post(f"/api/v1/{biz_id}/voice/campaigns", json={})).status_code == 401

    async def test_non_member_gets_403(self, client: AsyncClient, voice_env, stub_providers):
        """A member of another business never passes per-business RBAC."""
        env = voice_env
        headers = env["other_headers"]
        biz_id = env["biz_a"].id
        assert (
            await client.get(f"/api/v1/{biz_id}/voice/calls", headers=headers)
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/{biz_id}/voice/calls",
                headers=headers,
                json={"to_number": "+447700900123", "purpose": "BOOKING_REMINDER"},
            )
        ).status_code == 403
        assert (
            await client.get(f"/api/v1/{biz_id}/voice/campaigns", headers=headers)
        ).status_code == 403

    async def test_staff_cannot_access_admin_endpoints(self, client: AsyncClient, voice_env):
        env = voice_env
        headers = env["staff_headers"]
        biz_id = env["biz_a"].id
        assert (
            await client.post(
                f"/api/v1/{biz_id}/voice/agent-config",
                headers=headers,
                json={"enabled": True},
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/{biz_id}/voice/campaigns",
                headers=headers,
                json={"name": "X", "purpose": "SERVICE_PROMOTION"},
            )
        ).status_code == 403


# ── 2. Agent configuration ──


class TestAgentConfig:
    async def test_upsert_and_get(self, client: AsyncClient, voice_env):
        env = voice_env
        biz_id = env["biz_a"].id
        response = await client.post(
            f"/api/v1/{biz_id}/voice/agent-config",
            headers=env["owner_headers"],
            json={
                "enabled": True,
                "transactional_calling_enabled": True,
                "marketing_calling_enabled": True,
                "max_attempts": 4,
                "webhook_signature_secret": "s3cret-value",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["enabled"] is True
        assert body["max_attempts"] == 4
        # The webhook secret is write-only — never serialized.
        assert "webhook_signature_secret" not in body

        updated = await client.post(
            f"/api/v1/{biz_id}/voice/agent-config",
            headers=env["owner_headers"],
            json={"max_attempts": 2},
        )
        assert updated.status_code == 200
        assert updated.json()["max_attempts"] == 2

        fetched = await client.get(
            f"/api/v1/{biz_id}/voice/agent-config",
            headers=env["staff_headers"],
        )
        assert fetched.status_code == 200
        assert fetched.json()["max_attempts"] == 2
        assert "webhook_signature_secret" not in fetched.json()

    async def test_get_unconfigured_404(self, client: AsyncClient, voice_env):
        env = voice_env
        response = await client.get(
            f"/api/v1/businesses/{env['biz_a'].id}/voice/agent-config",
            headers=env["owner_headers"],
        )
        assert response.status_code == 404


# ── 3. Voice calls ──


async def post_call(client: AsyncClient, headers: dict, biz_id: uuid.UUID, **overrides) -> object:
    """POST a call request to the voice API."""
    payload = {
        "to_number": "+447700900123",
        "purpose": "BOOKING_REMINDER",
        **overrides,
    }
    return await client.post(f"/api/v1/{biz_id}/voice/calls", headers=headers, json=payload)


async def advance_to_connected(db_session: AsyncSession, provider, call_id: uuid.UUID) -> None:
    """Sync an initiated call to CONNECTED via the provider sequence."""
    call = await db_session.get(VoiceCall, call_id)
    orchestration = VoiceProviderOrchestrationService(db_session, provider)
    call = await orchestration.sync_provider_status(call, "ringing")
    await orchestration.sync_provider_status(call, "in-progress")
    await db_session.flush()


async def begun_connected_call(
    client: AsyncClient, env: dict, db_session: AsyncSession, provider
) -> uuid.UUID:
    """Create an API call, sync it to CONNECTED, begin a governed session."""
    await make_config(db_session, env["biz_a"].id)
    await make_brain(db_session, env["biz_a"], voice_agent=VOICE_AGENT_CONFIG)
    created = await post_call(client, env["owner_headers"], env["biz_a"].id)
    assert created.status_code == 201, created.text
    call_id = uuid.UUID(created.json()["id"])
    await advance_to_connected(db_session, provider, call_id)
    call = await db_session.get(VoiceCall, call_id)
    await VoiceCallAgent(db_session, ScriptedAI()).begin(call)
    return call_id


# ── 3. Voice calls ──


class TestCalls:
    async def test_request_and_initiate_call(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        await make_config(db_session, biz_id)

        response = await post_call(client, env["owner_headers"], biz_id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "INITIATING"
        assert body["provider"] == "stub"
        assert body["provider_reference"]
        assert body["purpose"] == "BOOKING_REMINDER"
        assert body["initiated_at"] is not None

        # Exactly one provider dial with the requested destination.
        assert len(stub_providers.requests) == 1
        assert stub_providers.requests[0].to == "+447700900123"

    async def test_request_without_initiation(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        await make_config(db_session, biz_id)

        response = await post_call(client, env["owner_headers"], biz_id, initiate=False)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "AUTHORIZED"
        assert body["provider_reference"] is None
        assert not stub_providers.requests

    async def test_idempotent_call_creation(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        await make_config(db_session, biz_id)
        key = f"test-{uuid.uuid4().hex}"

        first = await post_call(client, env["owner_headers"], biz_id, idempotency_key=key)
        assert first.status_code == 201, first.text
        second = await post_call(client, env["owner_headers"], biz_id, idempotency_key=key)
        assert second.status_code == 201, second.text

        assert second.json()["id"] == first.json()["id"]
        # The replay never dials the provider again.
        assert len(stub_providers.requests) == 1

    async def test_list_and_get_calls(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        await make_config(db_session, biz_id)

        first = await post_call(client, env["owner_headers"], biz_id, initiate=False)
        second = await post_call(client, env["owner_headers"], biz_id, initiate=False)
        assert first.status_code == 201 and second.status_code == 201

        listed = await client.get(
            f"/api/v1/{biz_id}/voice/calls",
            headers=env["owner_headers"],
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 2

        got = await client.get(
            f"/api/v1/{biz_id}/voice/calls/{first.json()['id']}",
            headers=env["owner_headers"],
        )
        assert got.status_code == 200
        assert got.json()["id"] == first.json()["id"]

        missing = await client.get(
            f"/api/v1/{biz_id}/voice/calls/{uuid.uuid4()}",
            headers=env["owner_headers"],
        )
        assert missing.status_code == 404

    async def test_cancel_call(self, client: AsyncClient, voice_env, db_session, stub_providers):
        env = voice_env
        biz_id = env["biz_a"].id
        await make_config(db_session, biz_id)

        created = await post_call(client, env["owner_headers"], biz_id, initiate=False)
        cancelled = await client.post(
            f"/api/v1/{biz_id}/voice/calls/{created.json()['id']}/cancel",
            headers=env["owner_headers"],
            json={"reason": "no longer needed"},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"


# ── 4. Call Agent conversation ──


class TestAgentTurn:
    async def test_governed_turn_end_to_end(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        call_id = await begun_connected_call(client, env, db_session, stub_providers)

        turn = await client.post(
            f"/api/v1/{biz_id}/voice/calls/{call_id}/turns",
            headers=env["owner_headers"],
            json={"utterance": "Hello, who is this?"},
        )
        assert turn.status_code == 200, turn.text
        body = turn.json()
        assert body["reply"] == "Understood."
        assert body["action"] == "CONTINUE"
        assert body["turn_count"] == 1
        # The governed conversation runtime moves the call into
        # IN_PROGRESS on the first turn.
        assert body["call_status"] == "IN_PROGRESS"

    async def test_turn_requires_active_session(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        await make_config(db_session, biz_id)
        await make_brain(db_session, env["biz_a"], voice_agent=VOICE_AGENT_CONFIG)
        created = await post_call(client, env["owner_headers"], biz_id)
        call_id = uuid.UUID(created.json()["id"])
        await advance_to_connected(db_session, stub_providers, call_id)

        turn = await client.post(
            f"/api/v1/{biz_id}/voice/calls/{call_id}/turns",
            headers=env["owner_headers"],
            json={"utterance": "Hello?"},
        )
        # No active session — the runtime rejects the turn (422).
        assert turn.status_code == 422


# ── 5. Outcome recording ──


class TestOutcome:
    async def test_record_outcome(self, client: AsyncClient, voice_env, db_session, stub_providers):
        env = voice_env
        biz_id = env["biz_a"].id
        call_id = await begun_connected_call(client, env, db_session, stub_providers)

        response = await client.post(
            f"/api/v1/{biz_id}/voice/calls/{call_id}/outcome",
            headers=env["owner_headers"],
            json={"outcome": "CONFIRMED", "summary": "Customer confirmed the booking."},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["outcome"] == "CONFIRMED"
        assert body["call_status"] == "IN_PROGRESS"

    async def test_unknown_outcome_rejected(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        call_id = await begun_connected_call(client, env, db_session, stub_providers)

        response = await client.post(
            f"/api/v1/{biz_id}/voice/calls/{call_id}/outcome",
            headers=env["owner_headers"],
            json={"outcome": "NOT_A_REAL_OUTCOME"},
        )
        assert response.status_code == 422


# ── 6. Escalations ──


class TestEscalations:
    async def test_escalation_lifecycle(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        call_id = await begun_connected_call(client, env, db_session, stub_providers)
        base = f"/api/v1/{biz_id}/voice/calls/{call_id}/escalations"

        created = await client.post(
            base,
            headers=env["owner_headers"],
            json={"reason": "Customer requested a human operator."},
        )
        assert created.status_code == 201, created.text
        assert created.json()["escalation_status"] == "REQUESTED"
        escalation_id = created.json()["id"]

        fetched = await client.get(
            f"/api/v1/{biz_id}/voice/calls/{call_id}",
            headers=env["owner_headers"],
        )
        assert fetched.json()["status"] == "ESCALATED"

        # Cross-business assignment is never possible — 404, not assigned.
        cross = await client.post(
            f"{base}/{escalation_id}/assign",
            headers=env["owner_headers"],
            json={"assigned_member_id": str(env["other_member_id"])},
        )
        assert cross.status_code == 404

        assigned = await client.post(
            f"{base}/{escalation_id}/assign",
            headers=env["owner_headers"],
            json={"assigned_member_id": str(env["staff_member_id"])},
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["escalation_status"] == "ASSIGNED"
        assert assigned.json()["assigned_member_id"] == str(env["staff_member_id"])

        accepted = await client.post(f"{base}/{escalation_id}/accept", headers=env["owner_headers"])
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["escalation_status"] == "ACCEPTED"

        resolved = await client.post(
            f"{base}/{escalation_id}/resolve",
            headers=env["owner_headers"],
            json={"resolution_notes": "Handled by the operator."},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["escalation_status"] == "RESOLVED"
        assert resolved.json()["resolution_notes"] == "Handled by the operator."

        listing = await client.get(base, headers=env["owner_headers"])
        assert listing.status_code == 200
        assert [e["escalation_status"] for e in listing.json()] == ["RESOLVED"]


# ── 7. Campaigns ──


class TestCampaigns:
    async def test_campaign_lifecycle_governed_activation(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz = env["biz_a"]
        await make_config(db_session, biz.id)
        version = await make_brain(db_session, biz)
        await setup_voice_policy(db_session, biz)
        base = f"/api/v1/{biz.id}/voice/campaigns"

        created = await client.post(
            base,
            headers=env["owner_headers"],
            json={
                "name": "Spring reactivation",
                "purpose": "SERVICE_PROMOTION",
                "brain_version_id": str(version.id),
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "DRAFT"
        campaign_id = created.json()["id"]

        # Staff may not transition campaigns (ADMIN+).
        staff_transition = await client.post(
            f"{base}/{campaign_id}/transition",
            headers=env["staff_headers"],
            json={"status": "ACTIVE"},
        )
        assert staff_transition.status_code == 403

        customer = await make_customer(db_session, biz)
        recipient = await client.post(
            f"{base}/{campaign_id}/recipients",
            headers=env["owner_headers"],
            json={"phone_number": "+447700900456", "customer_id": str(customer.id)},
        )
        assert recipient.status_code == 201, recipient.text
        assert recipient.json()["status"] == "PENDING"

        recipients = await client.get(
            f"{base}/{campaign_id}/recipients", headers=env["staff_headers"]
        )
        assert [r["status"] for r in recipients.json()] == ["PENDING"]

        # Governed activation: marketing campaigns without a governing
        # Brain version can never be activated.
        ungoverned = await client.post(
            base,
            headers=env["owner_headers"],
            json={"name": "Ungoverned", "purpose": "SERVICE_PROMOTION"},
        )
        assert ungoverned.status_code == 201
        rejected = await client.post(
            f"{base}/{ungoverned.json()['id']}/transition",
            headers=env["owner_headers"],
            json={"status": "ACTIVE"},
        )
        assert rejected.status_code == 422

        # Invalid transition: DRAFT -> COMPLETED is not in the state machine.
        invalid = await client.post(
            f"{base}/{campaign_id}/transition",
            headers=env["owner_headers"],
            json={"status": "COMPLETED"},
        )
        assert invalid.status_code == 422

        activated = await client.post(
            f"{base}/{campaign_id}/transition",
            headers=env["owner_headers"],
            json={"status": "ACTIVE"},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["status"] == "ACTIVE"

        executed = await client.post(f"{base}/{campaign_id}/execute", headers=env["owner_headers"])
        assert executed.status_code == 200, executed.text
        assert executed.json()["contacted"] == 1

        recipients = await client.get(
            f"{base}/{campaign_id}/recipients", headers=env["staff_headers"]
        )
        assert recipients.json()[0]["status"] == "CONTACTED"
        assert len(stub_providers.requests) == 1

        campaigns = await client.get(base, headers=env["staff_headers"])
        assert campaigns.status_code == 200
        assert len(campaigns.json()) == 2

        got = await client.get(f"{base}/{campaign_id}", headers=env["staff_headers"])
        assert got.status_code == 200
        assert got.json()["status"] == "ACTIVE"

        missing = await client.get(f"{base}/{uuid.uuid4()}", headers=env["staff_headers"])
        assert missing.status_code == 404


# ── 8. Provider webhooks ──


def _signed_headers(secret: str, body: bytes) -> dict[str, str]:
    return {"X-Voice-Signature": hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()}


class TestWebhook:
    async def test_signature_and_state_sync(
        self, client: AsyncClient, voice_env, db_session, stub_providers
    ):
        env = voice_env
        biz_id = env["biz_a"].id
        configured = await client.post(
            f"/api/v1/{biz_id}/voice/agent-config",
            headers=env["owner_headers"],
            json={
                "enabled": True,
                "transactional_calling_enabled": True,
                "default_from_number": "+441234567890",
                "webhook_signature_secret": "s3cret-value",
            },
        )
        assert configured.status_code == 200, configured.text

        created = await post_call(client, env["owner_headers"], biz_id)
        assert created.status_code == 201, created.text
        reference = created.json()["provider_reference"]
        webhook_url = "/api/v1/webhooks/voice/stub"

        # Unsigned callback — fail-closed 401, no state change.
        body = json.dumps({"CallSid": reference, "CallStatus": "ringing"}).encode()
        unsigned = await client.post(webhook_url, content=body)
        assert unsigned.status_code == 401

        # Signed callback — accepted and synchronized.
        signed = await client.post(
            webhook_url, content=body, headers=_signed_headers("s3cret-value", body)
        )
        assert signed.status_code == 202, signed.text
        assert signed.json()["status"] == "accepted"
        assert signed.json()["call_id"] == created.json()["id"]

        call = await client.get(
            f"/api/v1/{biz_id}/voice/calls/{created.json()['id']}",
            headers=env["owner_headers"],
        )
        assert call.json()["status"] == "RINGING"

        # Replayed event — idempotent duplicate acknowledgment.
        replay = await client.post(
            webhook_url, content=body, headers=_signed_headers("s3cret-value", body)
        )
        assert replay.status_code == 202
        assert replay.json()["status"] == "duplicate"

        # A distinct status is a distinct event.
        body2 = json.dumps({"CallSid": reference, "CallStatus": "in-progress"}).encode()
        connected = await client.post(
            webhook_url, content=body2, headers=_signed_headers("s3cret-value", body2)
        )
        assert connected.status_code == 202, connected.text

        call = await client.get(
            f"/api/v1/{biz_id}/voice/calls/{created.json()['id']}",
            headers=env["owner_headers"],
        )
        assert call.json()["status"] == "CONNECTED"

    async def test_mock_provider_exempt_from_signature(self, client: AsyncClient):
        response = await client.post("/api/v1/webhooks/voice/mock", json={"CallStatus": "queued"})
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "accepted"
        assert body["call_id"] is None

    async def test_invalid_json_rejected(self, client: AsyncClient):
        response = await client.post("/api/v1/webhooks/voice/mock", content=b"{not json")
        assert response.status_code == 400
