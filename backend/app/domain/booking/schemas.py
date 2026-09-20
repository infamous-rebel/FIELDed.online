"""Booking domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BookingCreate(BaseModel):
    """Request to create a booking from an accepted quote."""
    quote_id: uuid.UUID
    requested_at: datetime
    notes: str | None = None


class BookingRead(BaseModel):
    """Booking response."""
    id: uuid.UUID
    reference: str
    customer_id: uuid.UUID
    business_id: uuid.UUID
    quote_id: uuid.UUID
    enquiry_id: uuid.UUID
    service_offer_id: uuid.UUID
    requested_at: datetime
    currency: str
    status: str
    brain_version_id: uuid.UUID | None = None
    decision_evidence: dict | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookingTransitionRequest(BaseModel):
    """Request to transition a booking's lifecycle status."""
    target_status: str = Field(
        pattern=r"^(proposed|accepted|confirmed|in_progress|completed|declined|cancelled|expired|no_show)$",
        description="Target lifecycle status",
    )


class AvailabilityCheckRequest(BaseModel):
    """Request to check availability for a proposed booking time."""
    service_offer_id: uuid.UUID
    requested_at: datetime


class AvailabilityCheckResponse(BaseModel):
    """Response from an availability evaluation."""
    available: bool
    requested_at: datetime
    reason: str
    brain_version_id: uuid.UUID | None = None
    matched_rules: list[dict] = []
    blocked_by: list[str] = []


class BookingListRead(BaseModel):
    """Summary booking for list views."""
    id: uuid.UUID
    reference: str
    quote_id: uuid.UUID
    requested_at: datetime
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
