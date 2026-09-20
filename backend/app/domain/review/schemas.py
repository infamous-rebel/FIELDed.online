"""Review Pydantic schemas.

Request/response schemas for the Review API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    """Request schema for submitting a review."""

    service_execution_id: uuid.UUID = Field(
        ..., description="Completed service execution to review"
    )
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    title: str | None = Field(None, max_length=200, description="Review title")
    body: str | None = Field(None, description="Review body text")


class ReviewRead(BaseModel):
    """Read schema for a review."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    service_execution_id: uuid.UUID
    booking_id: uuid.UUID
    enquiry_id: uuid.UUID
    service_offer_id: uuid.UUID
    rating: int
    title: str | None = None
    body: str | None = None
    status: str
    response_body: str | None = None
    responded_at: datetime | None = None
    responded_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewRespondRequest(BaseModel):
    """Request schema for a business responding to a review."""

    response_body: str = Field(..., description="Business response text")


class ReviewListRead(BaseModel):
    """List wrapper for reviews."""

    items: list[ReviewRead]
    total: int | None = None


class PublicReviewRead(BaseModel):
    """Public-facing review schema (no internal IDs exposed)."""

    id: uuid.UUID
    rating: int
    title: str | None = None
    body: str | None = None
    response_body: str | None = None
    responded_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicReviewListRead(BaseModel):
    """List wrapper for public reviews."""

    items: list[PublicReviewRead]
    total: int | None = None
    average_rating: float | None = None
