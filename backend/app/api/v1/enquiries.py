"""Customer Enquiry API endpoints.

Provides enquiry creation, listing, conversation access, messaging,
and lifecycle transitions for authenticated customers.
All ownership is verified server-side — client-supplied IDs are
never trusted for authorization.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.common.enums import EnquiryStatus
from app.domain.enquiry.schemas import (
    ConversationWithMessages,
    EnquiryCreate,
    EnquiryRead,
    EnquiryTransitionRequest,
    MessageCreate,
    MessageRead,
)
from app.domain.enquiry.service import EnquiryService
from app.domain.identity.models import User
from app.exceptions import AuthorizationError
from app.security.authorization import get_current_user, require_customer

router = APIRouter()


def _enquiry_to_read(enquiry) -> EnquiryRead:
    """Convert an Enquiry model to the read schema."""
    return EnquiryRead.model_validate(enquiry)


def _message_to_read(msg) -> MessageRead:
    """Convert a Message model to the read schema."""
    return MessageRead.model_validate(msg)


# --- Enquiry CRUD ---


@router.post(
    "/{business_id}/enquiries",
    response_model=EnquiryRead,
    status_code=201,
)
async def create_enquiry(
    business_id: uuid.UUID,
    body: EnquiryCreate,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnquiryRead:
    """Create a new enquiry for a service offer.

    The server resolves all relationships (customer, business, service offer)
    and creates the enquiry + conversation atomically.
    """
    service = EnquiryService(db)

    enquiry = await service.create_enquiry(
        customer=user,
        business_id=business_id,
        service_offer_id=body.service_offer_id,
        subject=body.subject,
        message=body.message,
    )

    # Refresh to reload attributes expired by the flush
    await db.refresh(enquiry)
    return _enquiry_to_read(enquiry)


@router.get("/my-enquiries", response_model=list[EnquiryRead])
async def list_my_enquiries(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[EnquiryRead]:
    """List all enquiries for the authenticated customer."""
    service = EnquiryService(db)
    enquiries = await service.list_customer_enquiries(
        user.id, status=status, limit=limit, offset=offset
    )
    return [_enquiry_to_read(e) for e in enquiries]


@router.get(
    "/my-enquiries/{enquiry_id}",
    response_model=EnquiryRead,
)
async def get_my_enquiry(
    enquiry_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnquiryRead:
    """Get a specific enquiry owned by the authenticated customer."""
    service = EnquiryService(db)
    enquiry = await service.get_customer_enquiry(enquiry_id, user.id)
    return _enquiry_to_read(enquiry)


# --- Conversation ---


@router.get(
    "/my-enquiries/{enquiry_id}/conversation",
    response_model=ConversationWithMessages,
)
async def get_enquiry_conversation(
    enquiry_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationWithMessages:
    """Get the conversation (with messages) for a customer's enquiry."""
    service = EnquiryService(db)

    # Verify customer ownership
    enquiry = await service.get_customer_enquiry(enquiry_id, user.id)

    # Get conversation
    conversation = await service.get_enquiry_conversation(enquiry.id)

    # Get messages
    messages = await service.list_messages(conversation.id)

    return ConversationWithMessages(
        id=conversation.id,
        enquiry_id=conversation.enquiry_id,
        customer_id=conversation.customer_id,
        business_id=conversation.business_id,
        status=conversation.status,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[_message_to_read(m) for m in messages],
    )


# --- Messages ---


@router.get(
    "/my-enquiries/{enquiry_id}/messages",
    response_model=list[MessageRead],
)
async def list_enquiry_messages(
    enquiry_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[MessageRead]:
    """List messages in a customer's enquiry conversation."""
    service = EnquiryService(db)

    # Verify customer ownership
    enquiry = await service.get_customer_enquiry(enquiry_id, user.id)
    conversation = await service.get_enquiry_conversation(enquiry.id)

    messages = await service.list_messages(
        conversation.id, limit=limit, offset=offset
    )

    # Mark messages as read for this customer
    await service.mark_messages_read(conversation.id, user.id)

    return [_message_to_read(m) for m in messages]


@router.post(
    "/my-enquiries/{enquiry_id}/messages",
    response_model=MessageRead,
    status_code=201,
)
async def send_customer_message(
    enquiry_id: uuid.UUID,
    body: MessageCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageRead:
    """Send a message in a customer's enquiry conversation."""
    service = EnquiryService(db)

    # Verify customer ownership
    enquiry = await service.get_customer_enquiry(enquiry_id, user.id)
    conversation = await service.get_enquiry_conversation(enquiry.id)

    msg = await service.send_message(
        conversation=conversation,
        sender=user,
        sender_type="customer",
        content=body.content,
        message_type=body.message_type,
    )

    # Refresh to reload attributes expired by the flush
    await db.refresh(msg)
    return _message_to_read(msg)


# --- Lifecycle transitions ---


@router.post(
    "/my-enquiries/{enquiry_id}/transition",
    response_model=EnquiryRead,
)
async def transition_my_enquiry(
    enquiry_id: uuid.UUID,
    body: EnquiryTransitionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnquiryRead:
    """Transition a customer's enquiry lifecycle.

    Customers can primarily CANCEL their own enquiries.
    """
    service = EnquiryService(db)

    # Verify customer ownership
    enquiry = await service.get_customer_enquiry(enquiry_id, user.id)

    target_status = EnquiryStatus(body.target_status)
    enquiry = await service.transition_enquiry(enquiry, target_status, actor="customer")

    # Refresh to reload attributes expired by the flush
    await db.refresh(enquiry)
    return _enquiry_to_read(enquiry)
