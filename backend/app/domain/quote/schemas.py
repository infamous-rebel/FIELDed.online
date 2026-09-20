"""Quote domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _stringify_amount(v):
    """Coerce NUMERIC/Decimal amounts to their string API representation."""
    return str(v) if v is not None else v


class QuoteCreate(BaseModel):
    """Request to create a quote for an enquiry."""
    enquiry_id: uuid.UUID
    notes: str | None = None


class QuoteRead(BaseModel):
    """Quote response."""
    id: uuid.UUID
    reference: str
    customer_id: uuid.UUID
    business_id: uuid.UUID
    enquiry_id: uuid.UUID
    service_offer_id: uuid.UUID
    amount: str
    currency: str
    status: str
    brain_version_id: uuid.UUID | None = None
    pricing_evidence: dict | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    _coerce_amount = field_validator("amount", mode="before")(_stringify_amount)


class QuoteTransitionRequest(BaseModel):
    """Request to transition a quote's lifecycle status."""
    target_status: str = Field(
        pattern=r"^(issued|accepted|declined|expired)$",
        description="Target lifecycle status",
    )


class QuoteListRead(BaseModel):
    """Summary quote for list views."""
    id: uuid.UUID
    reference: str
    enquiry_id: uuid.UUID
    amount: str
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    _coerce_amount = field_validator("amount", mode="before")(_stringify_amount)
