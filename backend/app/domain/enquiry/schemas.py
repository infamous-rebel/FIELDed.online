"""Enquiry domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Enquiry schemas ---


class EnquiryCreate(BaseModel):
    """Request to create a new enquiry."""

    service_offer_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=10000)


class EnquiryRead(BaseModel):
    """Enquiry response."""

    id: uuid.UUID
    reference: str
    customer_id: uuid.UUID
    business_id: uuid.UUID
    service_offer_id: uuid.UUID
    subject: str
    message: str
    status: str
    metadata_: dict | None = None
    brain_version_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class EnquiryTransitionRequest(BaseModel):
    """Request to transition an enquiry's lifecycle status.

    Includes Phase 05 and Phase 12 reachable states.
    'rejected' is excluded as it has no valid inbound transition.
    """

    target_status: str = Field(
        pattern=r"^(submitted|received|in_review|needs_information|declined|cancelled|expired|quoted|customer_accepted|booking_proposed|booked|in_progress|completed)$",
        description="Target lifecycle status",
    )


# --- Conversation schemas ---


class ConversationRead(BaseModel):
    """Conversation response."""

    id: uuid.UUID
    enquiry_id: uuid.UUID
    customer_id: uuid.UUID
    business_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationWithMessages(ConversationRead):
    """Conversation including its messages."""

    messages: list[MessageRead] = []


# --- Message schemas ---


class MessageCreate(BaseModel):
    """Request to send a message."""

    content: str = Field(min_length=1, max_length=10000)
    message_type: str = Field(default="text", pattern=r"^text$")


class MessageRead(BaseModel):
    """Message response."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    sender_type: str
    content: str
    message_type: str
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Resolve forward reference
ConversationWithMessages.model_rebuild()
