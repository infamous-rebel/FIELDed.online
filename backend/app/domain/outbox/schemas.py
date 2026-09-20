"""Outbox domain Pydantic schemas.

Used for internal data transfer.  Outbox events are not directly
exposed via API endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OutboxEventRead(BaseModel):
    """Outbox event response (internal use)."""

    id: uuid.UUID
    business_id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict | None = None
    idempotency_key: str
    status: str
    attempt_count: int
    available_at: datetime
    processed_at: datetime | None = None
    last_error: str | None = None
    processing_started_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
