"""Phase 14B/14C voice API endpoints.

Voice calls, Call Agent configuration and conversation, escalations,
campaigns, provider webhooks, and Twilio TwiML transport.

All business-scoped endpoints enforce per-business RBAC
(owner > admin > staff) and tenant isolation via tenant-scoped
repositories.  The webhook endpoint authenticates via provider
signature verification, not user tokens.  Providers are constructed
per request from application settings — no global state.

Phase 14C adds Twilio TwiML transport endpoints (public, provider-
authenticated) that bridge live telephone audio to the existing
governed VoiceCallAgent.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import ProviderFactory
from app.adapters.voice.base import VoiceProvider
from app.database import get_db_session
from app.domain.common.enums import (
    BusinessMemberRole,
    CallStatus,
    CampaignStatus,
)
from app.domain.identity.models import BusinessMember
from app.domain.voice.agent import VoiceCallAgent
from app.domain.voice.campaign_execution import CampaignExecutionService
from app.domain.voice.campaign_service import CampaignService
from app.domain.voice.models import CallAgentConfiguration, VoiceCall
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.domain.voice.repository import (
    CallAgentConfigRepository,
    CampaignRecipientRepository,
    CampaignRepository,
    VoiceCallEscalationRepository,
    VoiceCallRepository,
)
from app.domain.voice.schemas import (
    AgentTurnRequest,
    AgentTurnResponse,
    CallAgentConfigRead,
    CallAgentConfigUpdate,
    CallCancelRequest,
    CallRequestCreate,
    CampaignCreate,
    CampaignRead,
    CampaignRecipientCreate,
    CampaignRecipientRead,
    CampaignTransitionRequest,
    EscalationAssignRequest,
    EscalationCancelRequest,
    EscalationCreateRequest,
    EscalationRead,
    EscalationResolveRequest,
    OutcomeRequest,
    VoiceCallRead,
)
from app.domain.voice.service import VoiceCallLifecycleService
from app.domain.voice.twiml import (
    error_response,
    gather_response,
    hangup_response,
    retry_gather_response,
    say_and_hangup_response,
)
from app.domain.voice.webhook_service import (
    VoiceWebhookService,
    compose_voice_event_id,
    verify_webhook_signature,
)
from app.security.authorization import require_business_role

router = APIRouter()

logger = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
StaffMember = Annotated[BusinessMember, Depends(require_business_role(BusinessMemberRole.STAFF))]
AdminMember = Annotated[BusinessMember, Depends(require_business_role(BusinessMemberRole.ADMIN))]


def _voice_provider(request: Request) -> VoiceProvider:
    """Resolve the voice provider from application settings per request."""
    factory = ProviderFactory.from_settings(request.app.state.settings)
    return factory.voice_provider


def _twiml_url(request: Request, call_id: uuid.UUID) -> str:
    """Build the public TwiML webhook URL for a call."""
    base = request.app.state.settings.public_base_url.rstrip("/")
    return f"{base}/api/v1/webhooks/voice/twilio/twiml/{call_id}"


def _gather_url(request: Request, call_id: uuid.UUID) -> str:
    """Build the public Gather callback URL for a call."""
    base = request.app.state.settings.public_base_url.rstrip("/")
    return f"{base}/api/v1/webhooks/voice/twilio/gather/{call_id}"


def _status_callback_url(request: Request, call_id: uuid.UUID) -> str:
    """Build the public status callback URL for a call."""
    base = request.app.state.settings.public_base_url.rstrip("/")
    return f"{base}/api/v1/webhooks/voice/twilio/status/{call_id}"


def _twilio_xml(twiml_str: str) -> FastAPIResponse:
    """Return a TwiML XML response with the correct content type."""
    return FastAPIResponse(
        content=f'<?xml version="1.0" encoding="UTF-8"?>{twiml_str}',
        media_type="application/xml",
    )


async def _verify_twilio_request(
    request: Request,
    call_id: uuid.UUID,
    settings,
) -> bool:
    """Verify a Twilio request signature for a TwiML/gather endpoint.

    Reconstructs the public URL from PUBLIC_BASE_URL + request path.
    Uses form parameters from the POST body.
    Returns True if valid, False otherwise.
    """
    from app.adapters.voice.twilio_security import verify_twilio_signature

    auth_token = settings.twilio_auth_token
    if not auth_token:
        logger.warning("twilio_signature_missing_auth_token")
        return False

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False

    base = settings.public_base_url.rstrip("/")
    url = f"{base}{request.url.path}"

    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    return verify_twilio_signature(url, params, auth_token, signature)


# ── Call Agent configuration ──


@router.post(
    "/{business_id}/voice/agent-config",
    response_model=CallAgentConfigRead,
)
async def upsert_agent_config(
    business_id: uuid.UUID,
    body: CallAgentConfigUpdate,
    member: AdminMember,
    db: DbSession,
) -> CallAgentConfigRead:
    """Create or update the Call Agent operational configuration."""
    repo = CallAgentConfigRepository(db)
    config = CallAgentConfiguration(business_id=business_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(config, field, value)
    result = await repo.upsert(config)
    await db.refresh(result)
    return CallAgentConfigRead.model_validate(result)


@router.get(
    "/{business_id}/voice/agent-config",
    response_model=CallAgentConfigRead,
)
async def get_agent_config(
    business_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
) -> CallAgentConfigRead:
    """Get the Call Agent operational configuration."""
    config = await CallAgentConfigRepository(db).get_for_business(business_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Call Agent not configured")
    return CallAgentConfigRead.model_validate(config)


# ── Voice calls ──


@router.post(
    "/{business_id}/voice/calls",
    response_model=VoiceCallRead,
    status_code=201,
)
async def request_call(
    business_id: uuid.UUID,
    body: CallRequestCreate,
    member: StaffMember,
    db: DbSession,
    request: Request,
) -> VoiceCallRead:
    """Request (and by default initiate) an outbound call.

    Idempotent when the client supplies ``idempotency_key``.
    """
    lifecycle = VoiceCallLifecycleService(db)
    idempotency_key = body.idempotency_key or (f"api:{member.user_id}:{uuid.uuid4().hex}")
    call = await lifecycle.request_call(
        business_id=business_id,
        to_number=body.to_number,
        purpose=body.purpose,
        provider=_voice_provider(request).provider_name,
        idempotency_key=idempotency_key,
        call_type=body.call_type,
        customer_id=body.customer_id,
        enquiry_id=body.enquiry_id,
        quote_id=body.quote_id,
        booking_id=body.booking_id,
        service_execution_id=body.service_execution_id,
        invoice_id=body.invoice_id,
        actor_id=member.user_id,
    )
    if call.status == "REQUESTED":
        call = await lifecycle.authorize_call(call, actor_id=member.user_id)
    if body.initiate:
        orchestration = VoiceProviderOrchestrationService(db, _voice_provider(request))
        twiml_url = _twiml_url(request, call.id)
        call = await orchestration.initiate_call(call, actor_id=member.user_id, twiml_url=twiml_url)
    await db.refresh(call)
    return VoiceCallRead.model_validate(call)


@router.get(
    "/{business_id}/voice/calls",
    response_model=list[VoiceCallRead],
)
async def list_calls(
    business_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
    status: str | None = Query(None),
    purpose: str | None = Query(None),
    call_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[VoiceCallRead]:
    """List voice calls for a business (tenant-scoped)."""
    calls = await VoiceCallRepository(db).list_for_business(
        business_id,
        call_type=call_type,
        purpose=purpose,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [VoiceCallRead.model_validate(c) for c in calls]


@router.get(
    "/{business_id}/voice/calls/{call_id}",
    response_model=VoiceCallRead,
)
async def get_call(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
) -> VoiceCallRead:
    """Get a voice call by ID (tenant-scoped)."""
    call = await VoiceCallRepository(db).get_by_id(call_id, business_id=business_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return VoiceCallRead.model_validate(call)


@router.post(
    "/{business_id}/voice/calls/{call_id}/cancel",
    response_model=VoiceCallRead,
)
async def cancel_call(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
    body: CallCancelRequest | None = None,
) -> VoiceCallRead:
    """Cancel a call (validated against the call state machine)."""
    call = await VoiceCallRepository(db).get_by_id(call_id, business_id=business_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    lifecycle = VoiceCallLifecycleService(db)
    call = await lifecycle.cancel_call(
        call,
        actor_id=member.user_id,
        reason=body.reason if body else None,
    )
    await db.refresh(call)
    return VoiceCallRead.model_validate(call)


# ── Call Agent conversation ──


@router.post(
    "/{business_id}/voice/calls/{call_id}/turns",
    response_model=AgentTurnResponse,
)
async def agent_turn(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    body: AgentTurnRequest,
    member: StaffMember,
    db: DbSession,
    request: Request,
) -> AgentTurnResponse:
    """Submit one conversation turn to the governed Call Agent."""
    call = await VoiceCallRepository(db).get_by_id(call_id, business_id=business_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    # Dynamic import keeps the AI resolution seam monkeypatchable in tests.
    from app.adapters import _resolve_call_agent_ai_provider

    ai_provider = _resolve_call_agent_ai_provider(request.app.state.settings)
    agent = VoiceCallAgent(db, ai_provider)
    result = await agent.handle_turn(call, body.utterance, actor_id=member.user_id)
    return AgentTurnResponse(
        reply=result["reply"],
        action=result["action"],
        outcome=result.get("outcome"),
        turn_count=result["turn_count"],
        call_status=result["call"].status,
    )


@router.post(
    "/{business_id}/voice/calls/{call_id}/outcome",
)
async def record_outcome(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    body: OutcomeRequest,
    member: StaffMember,
    db: DbSession,
    request: Request,
) -> dict:
    """Deterministically record the outcome of a call session."""
    call = await VoiceCallRepository(db).get_by_id(call_id, business_id=business_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    from app.adapters import _resolve_call_agent_ai_provider

    ai_provider = _resolve_call_agent_ai_provider(request.app.state.settings)
    agent = VoiceCallAgent(db, ai_provider)
    session_row = await agent.record_outcome(
        call, body.outcome, body.summary, actor_id=member.user_id
    )
    return {
        "outcome": session_row.outcome,
        "outcome_summary": session_row.outcome_summary,
        "call_status": call.status,
    }


# ── Escalations ──


@router.get(
    "/{business_id}/voice/calls/{call_id}/escalations",
    response_model=list[EscalationRead],
)
async def list_escalations(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
) -> list[EscalationRead]:
    """List escalations for a call."""
    call = await VoiceCallRepository(db).get_by_id(call_id, business_id=business_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    repo = VoiceCallEscalationRepository(db)
    escalation = await repo.get_for_call(call_id)
    return [EscalationRead.model_validate(escalation)] if escalation else []


@router.post(
    "/{business_id}/voice/calls/{call_id}/escalations",
    response_model=EscalationRead,
    status_code=201,
)
async def create_escalation(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    body: EscalationCreateRequest,
    member: StaffMember,
    db: DbSession,
) -> EscalationRead:
    """Escalate a connected call to a human (operator-initiated)."""
    call = await VoiceCallRepository(db).get_by_id(call_id, business_id=business_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    lifecycle = VoiceCallLifecycleService(db)
    await lifecycle.escalate_call(
        call,
        escalation_reason=body.reason,
        actor_id=member.user_id,
    )
    escalation = await VoiceCallEscalationRepository(db).get_for_call(call_id)
    assert escalation is not None
    return EscalationRead.model_validate(escalation)


async def _get_escalation_or_404(
    db: AsyncSession, business_id: uuid.UUID, escalation_id: uuid.UUID
):
    escalation = await VoiceCallEscalationRepository(db).get_by_id(
        escalation_id, business_id=business_id
    )
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return escalation


@router.post(
    "/{business_id}/voice/calls/{call_id}/escalations/{escalation_id}/assign",
    response_model=EscalationRead,
)
async def assign_escalation(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    escalation_id: uuid.UUID,
    body: EscalationAssignRequest,
    member: StaffMember,
    db: DbSession,
) -> EscalationRead:
    """Assign an escalation to a member of this business."""
    escalation = await _get_escalation_or_404(db, business_id, escalation_id)
    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.id == body.assigned_member_id,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Assigned member not found in this business")
    lifecycle = VoiceCallLifecycleService(db)
    escalation = await lifecycle.assign_escalation(
        escalation,
        assigned_member_id=body.assigned_member_id,
        actor_id=member.user_id,
    )
    return EscalationRead.model_validate(escalation)


@router.post(
    "/{business_id}/voice/calls/{call_id}/escalations/{escalation_id}/accept",
    response_model=EscalationRead,
)
async def accept_escalation(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    escalation_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
) -> EscalationRead:
    """Accept an escalation (the human handoff point)."""
    escalation = await _get_escalation_or_404(db, business_id, escalation_id)
    lifecycle = VoiceCallLifecycleService(db)
    escalation = await lifecycle.accept_escalation(escalation, actor_id=member.user_id)
    return EscalationRead.model_validate(escalation)


@router.post(
    "/{business_id}/voice/calls/{call_id}/escalations/{escalation_id}/resolve",
    response_model=EscalationRead,
)
async def resolve_escalation(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    escalation_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
    body: EscalationResolveRequest | None = None,
) -> EscalationRead:
    """Resolve an escalation."""
    escalation = await _get_escalation_or_404(db, business_id, escalation_id)
    lifecycle = VoiceCallLifecycleService(db)
    escalation = await lifecycle.resolve_escalation(
        escalation,
        resolution_notes=body.resolution_notes if body else None,
        actor_id=member.user_id,
    )
    return EscalationRead.model_validate(escalation)


@router.post(
    "/{business_id}/voice/calls/{call_id}/escalations/{escalation_id}/cancel",
    response_model=EscalationRead,
)
async def cancel_escalation(
    business_id: uuid.UUID,
    call_id: uuid.UUID,
    escalation_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
    body: EscalationCancelRequest | None = None,
) -> EscalationRead:
    """Cancel an escalation."""
    escalation = await _get_escalation_or_404(db, business_id, escalation_id)
    lifecycle = VoiceCallLifecycleService(db)
    escalation = await lifecycle.cancel_escalation(
        escalation,
        actor_id=member.user_id,
        reason=body.reason if body else None,
    )
    return EscalationRead.model_validate(escalation)


# ── Campaigns ──


@router.post(
    "/{business_id}/voice/campaigns",
    response_model=CampaignRead,
    status_code=201,
)
async def create_campaign(
    business_id: uuid.UUID,
    body: CampaignCreate,
    member: AdminMember,
    db: DbSession,
) -> CampaignRead:
    """Create a campaign in DRAFT status (ADMIN+)."""
    campaigns = CampaignService(db)
    campaign = await campaigns.create_campaign(
        business_id=business_id,
        name=body.name,
        channel="VOICE",
        purpose=body.purpose,
        description=body.description,
        start_at=body.start_at,
        end_at=body.end_at,
        brain_version_id=body.brain_version_id,
        created_by=member.user_id,
    )
    await db.refresh(campaign)
    return CampaignRead.model_validate(campaign)


@router.get(
    "/{business_id}/voice/campaigns",
    response_model=list[CampaignRead],
)
async def list_campaigns(
    business_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
    status: str | None = Query(None),
    purpose: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CampaignRead]:
    """List campaigns for a business (tenant-scoped)."""
    campaigns = await CampaignRepository(db).list_for_business(
        business_id, status=status, purpose=purpose, limit=limit, offset=offset
    )
    return [CampaignRead.model_validate(c) for c in campaigns]


@router.get(
    "/{business_id}/voice/campaigns/{campaign_id}",
    response_model=CampaignRead,
)
async def get_campaign(
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
) -> CampaignRead:
    """Get a campaign by ID (tenant-scoped)."""
    campaign = await CampaignRepository(db).get_by_id(campaign_id, business_id=business_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignRead.model_validate(campaign)


@router.post(
    "/{business_id}/voice/campaigns/{campaign_id}/transition",
    response_model=CampaignRead,
)
async def transition_campaign(
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    body: CampaignTransitionRequest,
    member: AdminMember,
    db: DbSession,
    request: Request,
) -> CampaignRead:
    """Transition a campaign (ADMIN+).

    Activation is governed:  an ACTIVE target routes through the
    execution service so the marketing/Brain-version and start_at
    gates are enforced.
    """
    campaign = await CampaignRepository(db).get_by_id(campaign_id, business_id=business_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaigns = CampaignService(db)
    target = body.status.upper()
    if target == CampaignStatus.ACTIVE.value:
        execution = CampaignExecutionService(db, _voice_provider(request))
        campaign = await execution.activate(campaign, actor_id=member.user_id)
    else:
        campaign = await campaigns.transition_campaign(campaign, CampaignStatus(target))
    await db.refresh(campaign)
    return CampaignRead.model_validate(campaign)


@router.post(
    "/{business_id}/voice/campaigns/{campaign_id}/recipients",
    response_model=CampaignRecipientRead,
    status_code=201,
)
async def add_campaign_recipient(
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    body: CampaignRecipientCreate,
    member: AdminMember,
    db: DbSession,
) -> CampaignRecipientRead:
    """Add a recipient to a campaign (eligibility evaluated at execution)."""
    campaign = await CampaignRepository(db).get_by_id(campaign_id, business_id=business_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    recipient = await CampaignService(db).add_recipient(
        campaign,
        phone_number=body.phone_number,
        customer_id=body.customer_id,
    )
    await db.refresh(recipient)
    return CampaignRecipientRead.model_validate(recipient)


@router.get(
    "/{business_id}/voice/campaigns/{campaign_id}/recipients",
    response_model=list[CampaignRecipientRead],
)
async def list_campaign_recipients(
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    member: StaffMember,
    db: DbSession,
) -> list[CampaignRecipientRead]:
    """List recipients of a campaign."""
    campaign = await CampaignRepository(db).get_by_id(campaign_id, business_id=business_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    recipients = await CampaignRecipientRepository(db).list_for_campaign(campaign_id)
    return [CampaignRecipientRead.model_validate(r) for r in recipients]


@router.post(
    "/{business_id}/voice/campaigns/{campaign_id}/execute",
)
async def execute_campaign(
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    member: AdminMember,
    db: DbSession,
    request: Request,
) -> dict:
    """Process every PENDING recipient of an ACTIVE campaign (ADMIN+)."""
    campaign = await CampaignRepository(db).get_by_id(campaign_id, business_id=business_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    execution = CampaignExecutionService(db, _voice_provider(request))
    return await execution.process_campaign(campaign, actor_id=member.user_id)


# ── Provider webhooks ──


def _extract_voice_event(payload: dict) -> tuple[str, str]:
    """Extract (provider call reference, event status) from a payload."""
    call_sid = (
        payload.get("CallSid")
        or payload.get("call_sid")
        or payload.get("CallUUID")
        or str(uuid.uuid4())
    )
    status = payload.get("CallStatus") or payload.get("Status") or "unknown"
    return str(call_sid), str(status)


@router.post("/webhooks/voice/{provider}", status_code=202)
async def receive_voice_webhook(
    provider: str,
    request: Request,
    db: DbSession,
) -> dict:
    """Receive a voice provider status callback.

    Authentication is via HMAC signature over the raw body using the
    receiving business's configured secret (fail-closed).  Events are
    persisted idempotently and drive call state synchronization.
    """
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    call_sid, status = _extract_voice_event(payload)
    external_event_id = compose_voice_event_id(call_sid, status)

    voice_provider = _voice_provider(request)
    orchestration = VoiceProviderOrchestrationService(db, voice_provider)
    service = VoiceWebhookService(db, orchestration=orchestration)
    call = await service.resolve_call(call_sid)

    if provider != "mock":
        secret = None
        if call is not None:
            config = await CallAgentConfigRepository(db).get_for_business(call.business_id)
            secret = config.webhook_signature_secret if config else None
        if not verify_webhook_signature(provider, raw, request.headers, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    result = await service.process_event(
        provider=provider,
        external_event_id=external_event_id,
        event_type=status,
        payload=payload,
        call=call,
    )
    logger.info(
        "voice_webhook_received",
        provider=provider,
        call_id=str(call.id) if call else None,
        event_status=status,
        outcome=result.get("status"),
    )
    return result


# ── Phase 14C — Twilio TwiML transport ──


# Call statuses where the TwiML transport may proceed with conversation.
_TWIML_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        CallStatus.INITIATING.value,
        CallStatus.RINGING.value,
        CallStatus.CONNECTED.value,
        CallStatus.IN_PROGRESS.value,
    }
)

# Call statuses that are terminal — no further conversation possible.
_TWIML_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        CallStatus.COMPLETED.value,
        CallStatus.FAILED.value,
        CallStatus.NO_ANSWER.value,
        CallStatus.BUSY.value,
        CallStatus.DECLINED.value,
        CallStatus.CANCELLED.value,
        CallStatus.EXPIRED.value,
        CallStatus.ESCALATED.value,
    }
)


async def _resolve_call_for_twiml(
    db: AsyncSession,
    call_id: uuid.UUID,
    call_sid: str | None,
) -> VoiceCall | None:
    """Resolve a VoiceCall for a TwiML callback.

    Uses the persisted provider_reference (CallSid) as the
    authoritative identifier.  The call_id in the URL is a hint;
    the CallSid from Twilio POST data is the provider-controlled
    truth.  If both are present, they must match.
    """
    from app.domain.voice.models import VoiceCall

    # Resolve by provider_reference (CallSid) — tenant-unscoped
    # because Twilio callbacks are system-authority events.
    if call_sid:
        from sqlalchemy import select as _select

        result = await db.execute(
            _select(VoiceCall).where(
                VoiceCall.provider_reference == call_sid,
                VoiceCall.deleted_at.is_(None),
            )
        )
        call = result.scalars().first()
        if call is not None:
            # Cross-check: if URL call_id doesn't match, fail closed
            if call.id != call_id:
                logger.warning(
                    "twilio_call_id_mismatch",
                    extra={
                        "url_call_id": str(call_id),
                        "resolved_call_id": str(call.id),
                    },
                )
                return None
            return call

    # Fallback: resolve by call_id alone (no business scope — Twilio
    # callbacks are system-authority; tenant isolation is preserved
    # because the call_id is embedded in the signed URL).
    result = await db.execute(
        select(VoiceCall).where(
            VoiceCall.id == call_id,
            VoiceCall.deleted_at.is_(None),
        )
    )
    return result.scalars().first()


@router.post("/webhooks/voice/twilio/twiml/{call_id}")
async def twilio_twiml_webhook(
    call_id: uuid.UUID,
    request: Request,
    db: DbSession,
) -> FastAPIResponse:
    """Initial TwiML webhook — called by Twilio when the call connects.

    Returns TwiML with a greeting and <Gather input="speech">.
    Authenticates via Twilio signature verification.
    """
    settings = request.app.state.settings

    # Signature verification (fail-closed for non-mock providers)
    if (
        settings.voice_provider == "twilio"
        and settings.twilio_auth_token
        and not await _verify_twilio_request(request, call_id, settings)
    ):
        logger.warning("twilio_twiml_invalid_signature", extra={"call_id": str(call_id)})
        return _twilio_xml(error_response(message="Unauthorized."))

    form = await request.form()
    call_sid = form.get("CallSid") or form.get("CallUUID")

    call = await _resolve_call_for_twiml(db, call_id, str(call_sid) if call_sid else None)
    if call is None:
        logger.warning("twilio_twiml_call_not_found", extra={"call_id": str(call_id)})
        return _twilio_xml(error_response())

    # Terminal state — cannot converse
    if call.status in _TWIML_TERMINAL_STATUSES:
        logger.info(
            "twilio_twiml_terminal_call",
            extra={"call_id": str(call_id), "status": call.status},
        )
        return _twilio_xml(hangup_response())

    # Drive the call to CONNECTED if the status callback hasn't arrived yet
    lifecycle = VoiceCallLifecycleService(db)
    current_status = CallStatus(call.status)
    if current_status in (CallStatus.INITIATING, CallStatus.RINGING):
        if current_status is CallStatus.INITIATING:
            call = await lifecycle.mark_ringing(call, reason="twilio twiml webhook")
        call = await lifecycle.mark_connected(call, reason="twilio twiml webhook")

    # Start the agent session if not already active
    from app.domain.voice.repository import VoiceCallSessionRepository

    session_repo = VoiceCallSessionRepository(db)
    active_session = await session_repo.get_active_for_call(call.id)

    if active_session is None:
        # Initialize governed agent session
        from app.adapters import _resolve_call_agent_ai_provider

        ai_provider = _resolve_call_agent_ai_provider(settings)
        agent = VoiceCallAgent(db, ai_provider)
        try:
            active_session = await agent.begin(call)
        except Exception as exc:
            logger.error(
                "twilio_twiml_agent_begin_failed",
                extra={"call_id": str(call_id), "error": str(exc)},
            )
            return _twilio_xml(error_response(message="Sorry, the call agent is unavailable."))

    # Deterministic greeting — not LLM-generated
    from app.domain.identity.models import Business

    business = await db.get(Business, call.business_id)
    business_name = business.name if business else "the business"
    greeting = f"Hello, this is {business_name}. Please tell me how I can help you today."

    gather_url = _gather_url(request, call.id)
    twiml = gather_response(say_text=greeting, gather_action_url=gather_url)
    return _twilio_xml(twiml)


@router.post("/webhooks/voice/twilio/gather/{call_id}")
async def twilio_gather_callback(
    call_id: uuid.UUID,
    request: Request,
    db: DbSession,
) -> FastAPIResponse:
    """Gather speech callback — receives Twilio speech recognition results.

    Extracts the transcript, passes it to the existing VoiceCallAgent,
    and returns TwiML with the agent's reply (<Say>) followed by
    another <Gather>.
    """
    settings = request.app.state.settings

    # Signature verification
    if (
        settings.voice_provider == "twilio"
        and settings.twilio_auth_token
        and not await _verify_twilio_request(request, call_id, settings)
    ):
        logger.warning("twilio_gather_invalid_signature", extra={"call_id": str(call_id)})
        return _twilio_xml(error_response(message="Unauthorized."))

    form = await request.form()
    call_sid = form.get("CallSid") or form.get("CallUUID")
    speech_result = (form.get("SpeechResult") or "").strip()

    call = await _resolve_call_for_twiml(db, call_id, str(call_sid) if call_sid else None)
    if call is None:
        logger.warning("twilio_gather_call_not_found", extra={"call_id": str(call_id)})
        return _twilio_xml(error_response())

    # Terminal state
    if call.status in _TWIML_TERMINAL_STATUSES:
        return _twilio_xml(hangup_response())

    gather_url = _gather_url(request, call.id)

    # Empty / failed speech input — deterministic retry, no LLM
    if not speech_result:
        return _twilio_xml(retry_gather_response(gather_action_url=gather_url))

    # Pass transcript to the existing governed Call Agent
    from app.adapters import _resolve_call_agent_ai_provider

    ai_provider = _resolve_call_agent_ai_provider(settings)
    agent = VoiceCallAgent(db, ai_provider)

    try:
        result = await agent.handle_turn(call, speech_result)
    except Exception as exc:
        logger.error(
            "twilio_gather_agent_turn_failed",
            extra={"call_id": str(call_id), "error": str(exc)},
        )
        return _twilio_xml(
            error_response(message="Sorry, I encountered an error. Please try again.")
        )

    reply = result["reply"]
    action = result["action"]
    call_after = result["call"]

    # If the agent ended the call or requested escalation, hang up
    if action in ("END_CALL", "REQUEST_HUMAN"):
        twiml = say_and_hangup_response(say_text=reply)
        return _twilio_xml(twiml)

    # If the call is now terminal, hang up
    if call_after.status in _TWIML_TERMINAL_STATUSES:
        twiml = say_and_hangup_response(say_text=reply)
        return _twilio_xml(twiml)

    # Normal continuation: Say + Gather
    twiml = gather_response(say_text=reply, gather_action_url=gather_url)
    return _twilio_xml(twiml)


@router.post("/webhooks/voice/twilio/status/{call_id}")
async def twilio_status_callback(
    call_id: uuid.UUID,
    request: Request,
    db: DbSession,
) -> dict:
    """Twilio status callback — receives call status updates.

    Feeds into the existing webhook processing pipeline.
    Accepts form-encoded data from Twilio's StatusCallback parameter.
    """
    settings = request.app.state.settings

    form = await request.form()
    call_sid = str(form.get("CallSid") or form.get("CallUUID") or "")
    call_status = str(form.get("CallStatus") or "unknown")

    # Verify signature
    if (
        settings.voice_provider == "twilio"
        and settings.twilio_auth_token
        and not await _verify_twilio_request(request, call_id, settings)
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    external_event_id = compose_voice_event_id(call_sid, call_status)

    voice_provider = _voice_provider(request)
    orchestration = VoiceProviderOrchestrationService(db, voice_provider)
    service = VoiceWebhookService(db, orchestration=orchestration)

    call = await service.resolve_call(call_sid)
    if call is None:
        # Try resolving by call_id
        result = await db.execute(
            select(VoiceCall).where(
                VoiceCall.id == call_id,
                VoiceCall.deleted_at.is_(None),
            )
        )
        call = result.scalars().first()

    if call is None:
        logger.warning("twilio_status_call_not_found", extra={"call_id": str(call_id)})
        return {"status": "not_found"}

    result = await service.process_event(
        provider="twilio",
        external_event_id=external_event_id,
        event_type=call_status,
        payload=dict(form),
        call=call,
    )
    logger.info(
        "twilio_status_callback_received",
        extra={
            "call_id": str(call_id),
            "call_status": call_status,
            "outcome": result.get("status"),
        },
    )
    return result
