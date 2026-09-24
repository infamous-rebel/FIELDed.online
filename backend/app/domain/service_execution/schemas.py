"""Service Execution Pydantic schemas.

Request/response schemas for the Service Execution API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ServiceExecutionRead(BaseModel):
    """Read schema for a service execution."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    booking_id: uuid.UUID
    service_offer_id: uuid.UUID
    quote_id: uuid.UUID | None = None
    status: str
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by: uuid.UUID | None = None
    completion_evidence: dict[str, Any] | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceExecutionCreate(BaseModel):
    """Request schema for creating a service execution from a booking."""

    booking_id: uuid.UUID


class ServiceExecutionTransitionRequest(BaseModel):
    """Request schema for transitioning a service execution."""

    target_status: str = Field(..., description="Target status (in_progress, completed, cancelled, no_show)")
    notes: str | None = None
    completion_evidence: dict[str, Any] | None = None


class ServiceExecutionListRead(BaseModel):
    """List wrapper for service executions."""

    items: list[ServiceExecutionRead]
    total: int | None = None
