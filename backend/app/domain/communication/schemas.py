"""Communication domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── Communication ──


class CommunicationRead(BaseModel):
    """Communication response."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    channel: str
    purpose: str
    status: str
    idempotency_key: str
    brain_version_id: uuid.UUID | None = None
    decision_evidence: dict | None = None
    enquiry_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None
    booking_id: uuid.UUID | None = None
    service_execution_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None
    provider_reference: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CommunicationListRead(BaseModel):
    """Summary communication for list views."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    channel: str
    purpose: str
    status: str
    provider_reference: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommunicationAttemptRead(BaseModel):
    """Communication attempt response."""

    id: uuid.UUID
    communication_id: uuid.UUID
    provider_name: str
    provider_reference: str | None = None
    status: str
    error: str | None = None
    retry_count: int
    provider_response: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Recipients ──


class CommunicationRecipientRead(BaseModel):
    """Communication recipient response."""

    id: uuid.UUID
    communication_id: uuid.UUID
    user_id: uuid.UUID | None = None
    recipient_type: str
    channel: str
    address: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Templates ──


class CommunicationTemplateCreate(BaseModel):
    """Request to create a communication template."""

    channel: str
    purpose: str
    name: str = Field(min_length=1, max_length=255)
    subject: str | None = None
    body: str = Field(min_length=1)
    variables: dict | None = None


class CommunicationTemplateUpdate(BaseModel):
    """Request to update a communication template."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = None
    body: str | None = None
    variables: dict | None = None


class CommunicationTemplateVersionRead(BaseModel):
    """Template version response."""

    id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    subject: str | None = None
    body: str
    variables: dict | None = None
    approval_provenance: dict | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommunicationTemplateRead(BaseModel):
    """Template response."""

    id: uuid.UUID
    business_id: uuid.UUID
    channel: str
    purpose: str
    name: str
    active_version_id: uuid.UUID | None = None
    status: str
    approval_state: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Configuration ──


class BusinessChannelConfigRead(BaseModel):
    """Business channel configuration response."""

    id: uuid.UUID
    business_id: uuid.UUID
    channel: str
    enabled: bool
    provider_ref: str | None = None
    settings: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BusinessChannelConfigUpdate(BaseModel):
    """Request to update channel configuration."""

    enabled: bool | None = None
    provider_ref: str | None = None
    settings: dict | None = None


class BusinessPurposeConfigRead(BaseModel):
    """Business purpose configuration response."""

    id: uuid.UUID
    business_id: uuid.UUID
    purpose: str
    enabled: bool
    permitted_channels: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BusinessPurposeConfigUpdate(BaseModel):
    """Request to update purpose configuration."""

    enabled: bool | None = None
    permitted_channels: dict | None = None


# ── Consent / Preferences ──


class CustomerPreferenceRead(BaseModel):
    """Customer communication preference response."""

    id: uuid.UUID
    customer_id: uuid.UUID
    business_id: uuid.UUID
    channel: str | None = None
    purpose: str | None = None
    consent_state: str
    opt_in: bool
    suppression: bool
    suppression_reason: str | None = None
    do_not_contact: bool
    source: str | None = None
    consented_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerPreferenceUpdate(BaseModel):
    """Request to update customer communication preferences."""

    channel: str | None = None
    purpose: str | None = None
    consent_state: str | None = None
    opt_in: bool | None = None
    suppression: bool | None = None
    suppression_reason: str | None = None
    do_not_contact: bool | None = None
    source: str | None = None


class OptInRequest(BaseModel):
    """Request to opt in to communication."""

    channel: str | None = None
    purpose: str | None = None
    business_id: uuid.UUID


class OptOutRequest(BaseModel):
    """Request to opt out of communication."""

    channel: str | None = None
    purpose: str | None = None
    business_id: uuid.UUID


# ── Audit ──


class CommunicationAuditRead(BaseModel):
    """Communication audit event response."""

    id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None = None
    business_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    channel: str | None = None
    purpose: str | None = None
    communication_id: uuid.UUID | None = None
    brain_version_id: uuid.UUID | None = None
    decision_evidence: dict | None = None
    provider_reference: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
