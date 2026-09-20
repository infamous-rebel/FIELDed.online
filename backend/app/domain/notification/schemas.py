"""Notification domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    """Notification response."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    notification_type: str
    title: str
    body: str
    priority: str
    idempotency_key: str
    related_entity_type: str | None = None
    related_entity_id: uuid.UUID | None = None
    read_at: datetime | None = None
    delivery_state: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationListRead(BaseModel):
    """Summary notification for list views."""

    id: uuid.UUID
    business_id: uuid.UUID
    notification_type: str
    title: str
    priority: str
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    """Unread notification count."""

    unread_count: int
