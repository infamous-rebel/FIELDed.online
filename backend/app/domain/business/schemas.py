"""Business Brain domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- BusinessBrain schemas ---


class BusinessBrainRead(BaseModel):
    """Schema for business brain response."""

    id: uuid.UUID
    business_id: uuid.UUID
    active_version_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BusinessBrainDetailRead(BaseModel):
    """Brain response including the active version's details."""

    id: uuid.UUID
    business_id: uuid.UUID
    active_version_id: uuid.UUID | None = None
    active_version: BrainVersionRead | None = None
    version_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- BrainVersion schemas ---


class BrainVersionBase(BaseModel):
    """Base brain version fields."""

    identity_config: dict | None = None
    services_config: dict | None = None
    pricing_config: dict | None = None
    availability_config: dict | None = None
    qualification_config: dict | None = None
    policies_config: dict | None = None
    escalation_config: dict | None = None
    communication_config: dict | None = None


class BrainVersionCreate(BaseModel):
    """Schema for creating a new brain version.

    Accepts a unified config dict that is split into area columns.
    """

    config: dict | None = None


class BrainVersionUpdate(BaseModel):
    """Schema for updating a DRAFT brain version's configuration."""

    identity_config: dict | None = None
    services_config: dict | None = None
    pricing_config: dict | None = None
    availability_config: dict | None = None
    qualification_config: dict | None = None
    policies_config: dict | None = None
    escalation_config: dict | None = None
    communication_config: dict | None = None


class BrainVersionRead(BrainVersionBase):
    """Schema for brain version response."""

    id: uuid.UUID
    brain_id: uuid.UUID
    version_number: int
    status: str
    rules: list[BusinessRuleRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BrainVersionSummaryRead(BrainVersionBase):
    """Lightweight version response for list endpoints (no rules)."""

    id: uuid.UUID
    brain_id: uuid.UUID
    version_number: int
    status: str
    rule_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- BusinessRule schemas ---


class BusinessRuleBase(BaseModel):
    """Base business rule fields."""

    rule_type: str = Field(
        pattern=r"^(pricing|policy|qualification|availability|escalation)$"
    )
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rule_data: dict = Field(default_factory=dict)
    priority: int = 0
    is_active: bool = True


class BusinessRuleCreate(BusinessRuleBase):
    """Schema for creating a business rule."""

    pass


class BusinessRuleUpdate(BaseModel):
    """Schema for updating a business rule (partial)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    rule_data: dict | None = None
    priority: int | None = None
    is_active: bool | None = None


class BusinessRuleRead(BusinessRuleBase):
    """Schema for business rule response."""

    id: uuid.UUID
    brain_version_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Lifecycle / transition schemas ---


class BrainVersionTransitionRequest(BaseModel):
    """Request body for a lifecycle transition."""

    target_status: str = Field(
        ...,
        description="Target lifecycle status (e.g. validating, review, approved)",
    )


class BrainVersionTransitionRead(BaseModel):
    """Response after a successful lifecycle transition."""

    id: uuid.UUID
    previous_status: str
    current_status: str
    version_number: int


# --- Validation schemas ---


class ValidationErrorDetail(BaseModel):
    """A single structural validation error."""

    field: str
    message: str
    code: str


class ValidationResultRead(BaseModel):
    """Structured validation result."""

    valid: bool
    error_count: int
    errors: list[ValidationErrorDetail] = []


# --- Approval schemas ---


class ApprovalRequest(BaseModel):
    """Request body for approving a brain version."""

    comment: str | None = None


class ApprovalResultRead(BaseModel):
    """Response after an approval attempt."""

    decision: str
    version_id: uuid.UUID
    version_status: str
    approver_role: str
    comment: str | None = None


# --- Provenance schemas ---


class ProvenanceEntryRead(BaseModel):
    """A provenance/audit entry for a brain version."""

    action: str
    actor_id: uuid.UUID | None = None
    timestamp: datetime
    details: dict = {}


class ProvenanceRead(BaseModel):
    """Provenance information for a brain version."""

    version_id: uuid.UUID
    brain_id: uuid.UUID
    version_number: int
    status: str
    entries: list[ProvenanceEntryRead] = []
