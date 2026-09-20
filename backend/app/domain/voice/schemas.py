"""Phase 14B voice API schemas.

Request/response contracts for the voice-call, Call Agent, escalation,
campaign, and webhook endpoints.  All response schemas validate from
ORM attributes; secrets (``webhook_signature_secret``) are write-only
and never serialized back to clients.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Call Agent configuration ──


class CallAgentConfigUpdate(BaseModel):
    """Operational Call Agent configuration (ADMIN+ upsert).

    ``webhook_signature_secret`` is write-only:  it configures provider
    webhook authentication and is never returned by any endpoint.
    """

    enabled: bool | None = None
    transactional_calling_enabled: bool | None = None
    marketing_calling_enabled: bool | None = None
    default_from_number: str | None = None
    provider_reference: str | None = None
    timezone: str | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    retry_interval_seconds: int | None = Field(default=None, ge=0, le=86400)
    allowed_calling_hours: dict | None = None
    quiet_periods: list[dict] | None = None
    max_daily_attempts: int | None = Field(default=None, ge=1)
    max_weekly_attempts: int | None = Field(default=None, ge=1)
    customer_frequency_limits: dict | None = None
    human_escalation_enabled: bool | None = None
    recording_enabled: bool | None = None
    transcription_enabled: bool | None = None
    agent_instructions: str | None = Field(default=None, max_length=10000)
    webhook_signature_secret: str | None = Field(default=None, max_length=255)


class CallAgentConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    enabled: bool
    transactional_calling_enabled: bool
    marketing_calling_enabled: bool
    default_from_number: str | None = None
    provider_reference: str | None = None
    timezone: str | None = None
    max_attempts: int
    retry_interval_seconds: int
    allowed_calling_hours: dict | None = None
    quiet_periods: list[dict] | None = None
    max_daily_attempts: int | None = None
    max_weekly_attempts: int | None = None
    customer_frequency_limits: dict | None = None
    human_escalation_enabled: bool
    recording_enabled: bool
    transcription_enabled: bool
    agent_instructions: str | None = None
    created_at: datetime
    updated_at: datetime


# ── Voice calls ──


class CallRequestCreate(BaseModel):
    """A new outbound call request.

    ``idempotency_key`` is optional — when omitted the server derives
    one from the authenticated context so retries stay idempotent.
    """

    to_number: str = Field(min_length=3, max_length=50)
    purpose: str
    call_type: str | None = None
    customer_id: uuid.UUID | None = None
    enquiry_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    service_execution_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=500)
    initiate: bool = True


class VoiceCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    call_type: str
    purpose: str
    status: str
    to_number: str
    from_number: str | None = None
    provider: str
    provider_reference: str | None = None
    brain_version_id: uuid.UUID | None = None
    communication_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    enquiry_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    service_execution_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None
    requested_at: datetime
    authorized_at: datetime | None = None
    queued_at: datetime | None = None
    initiated_at: datetime | None = None
    connected_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CallCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


# ── Call Agent conversation ──


class AgentTurnRequest(BaseModel):
    utterance: str = Field(min_length=1, max_length=10000)


class AgentTurnResponse(BaseModel):
    reply: str
    action: str
    outcome: str | None = None
    turn_count: int
    call_status: str


class OutcomeRequest(BaseModel):
    outcome: str
    summary: str | None = Field(default=None, max_length=5000)


# ── Escalations ──


class EscalationCreateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class EscalationAssignRequest(BaseModel):
    assigned_member_id: uuid.UUID


class EscalationResolveRequest(BaseModel):
    resolution_notes: str | None = Field(default=None, max_length=5000)


class EscalationCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    call_id: uuid.UUID
    escalation_status: str
    escalation_reason: str
    requested_at: datetime
    assigned_member_id: uuid.UUID | None = None
    accepted_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    created_at: datetime


# ── Campaigns ──


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    purpose: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    brain_version_id: uuid.UUID | None = None


class CampaignTransitionRequest(BaseModel):
    status: str


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    description: str | None = None
    channel: str
    purpose: str
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    brain_version_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class CampaignRecipientCreate(BaseModel):
    phone_number: str = Field(min_length=3, max_length=50)
    customer_id: uuid.UUID | None = None


class CampaignRecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    phone_number: str
    status: str
    attempt_count: int
    last_attempt_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
