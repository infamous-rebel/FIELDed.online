"""Business Brain Interactive Co-Brain API endpoints.

Provides authenticated Brain conversation management:
- Start/list conversations
- Send messages and receive Brain responses
- Manage proposals (approve/reject)

All endpoints enforce tenant isolation through authorization dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import _resolve_brain_ai_provider
from app.config import get_settings
from app.database import get_db_session
from app.domain.business.auth import require_brain_access, require_brain_modify
from app.domain.business.conversation_service import BrainConversationService
from app.domain.business.models import (
    BrainConversation,
    BrainMessage,
    BrainProposal,
    BusinessBrain,
)
from app.domain.identity.models import User
from app.security.authorization import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BrainMessageRead(BaseModel):
    """Schema for reading a Brain message."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    metadata: dict | None = Field(None, alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class BrainConversationRead(BaseModel):
    """Schema for reading a Brain conversation."""

    id: uuid.UUID
    brain_id: uuid.UUID
    business_id: uuid.UUID
    status: str
    title: str | None = None
    context_summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BrainConversationDetailRead(BaseModel):
    """Schema for reading a Brain conversation with messages."""

    id: uuid.UUID
    brain_id: uuid.UUID
    business_id: uuid.UUID
    status: str
    title: str | None = None
    context_summary: str | None = None
    messages: list[BrainMessageRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BrainConversationSummaryRead(BaseModel):
    """Schema for conversation list items."""

    id: uuid.UUID
    brain_id: uuid.UUID
    status: str
    title: str | None = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    """Request body for sending an owner message."""

    content: str = Field(..., min_length=1, max_length=10000)


class SendMessageResponse(BaseModel):
    """Response after sending a message."""

    owner_message: BrainMessageRead
    brain_message: BrainMessageRead


class BrainProposalRead(BaseModel):
    """Schema for reading a Brain proposal."""

    id: uuid.UUID
    brain_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    business_id: uuid.UUID
    proposal_type: str
    status: str
    confidence: float
    reasoning_summary: str | None = None
    proposed_change: dict
    affected_area: str | None = None
    source_message_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    is_urgent: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApproveProposalRequest(BaseModel):
    """Request body for approving a proposal with optional edits."""

    edited_change: dict | None = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_brain_conversation_service(
    db: AsyncSession,
) -> BrainConversationService:
    """Create a BrainConversationService with the configured AI provider."""
    settings = get_settings()
    ai_provider = _resolve_brain_ai_provider(settings)
    return BrainConversationService(db, ai_provider)


def _message_to_read(message: BrainMessage) -> BrainMessageRead:
    """Convert a BrainMessage model to the read schema."""
    return BrainMessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        metadata_=message.metadata_,
        created_at=message.created_at,
    )


def _conversation_to_read(
    conversation: BrainConversation,
) -> BrainConversationDetailRead:
    """Convert a BrainConversation model to the detail read schema."""
    messages = [_message_to_read(m) for m in (conversation.messages or [])]
    return BrainConversationDetailRead(
        id=conversation.id,
        brain_id=conversation.brain_id,
        business_id=conversation.business_id,
        status=conversation.status,
        title=conversation.title,
        context_summary=conversation.context_summary,
        messages=messages,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _conversation_to_summary(
    conversation: BrainConversation,
) -> BrainConversationSummaryRead:
    """Convert a BrainConversation to the summary schema."""
    return BrainConversationSummaryRead(
        id=conversation.id,
        brain_id=conversation.brain_id,
        status=conversation.status,
        title=conversation.title,
        message_count=len(conversation.messages) if conversation.messages else 0,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _proposal_to_read(proposal: BrainProposal) -> BrainProposalRead:
    """Convert a BrainProposal model to the read schema."""
    return BrainProposalRead(
        id=proposal.id,
        brain_id=proposal.brain_id,
        conversation_id=proposal.conversation_id,
        business_id=proposal.business_id,
        proposal_type=proposal.proposal_type,
        status=proposal.status,
        confidence=proposal.confidence,
        reasoning_summary=proposal.reasoning_summary,
        proposed_change=proposal.proposed_change,
        affected_area=proposal.affected_area,
        source_message_id=proposal.source_message_id,
        resolved_at=proposal.resolved_at,
        is_urgent=proposal.is_urgent,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


# ---------------------------------------------------------------------------
# Conversation Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/brain/conversations",
    response_model=list[BrainConversationSummaryRead],
)
async def list_conversations(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[BrainConversationSummaryRead]:
    """List conversations for this business's Brain.

    Requires brain read access (any business member role).
    """
    service = _get_brain_conversation_service(
        brain.app_session  # type: ignore[attr-defined]
    )
    conversations = await service.list_conversations(brain.id)
    return [_conversation_to_summary(c) for c in conversations]


@router.get(
    "/{business_id}/brain/conversations/active",
    response_model=BrainConversationDetailRead,
)
async def get_active_conversation(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrainConversationDetailRead:
    """Get or create the active conversation for this Brain.

    This is the primary entry point for the Brain conversation UI.
    If no active conversation exists, one is created with an initial greeting.
    """
    service = _get_brain_conversation_service(db)
    conversation = await service.get_or_create_active_conversation(
        brain.id, brain.business_id
    )
    # Reload with messages
    from app.domain.business.repository import BrainConversationRepository

    repo = BrainConversationRepository(db)
    conversation = await repo.get_by_id(conversation.id)
    return _conversation_to_read(conversation)  # type: ignore[arg-type]


@router.get(
    "/{business_id}/brain/conversations/{conversation_id}",
    response_model=BrainConversationDetailRead,
)
async def get_conversation(
    conversation_id: uuid.UUID,
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrainConversationDetailRead:
    """Get a specific conversation with messages."""
    from app.domain.business.repository import BrainConversationRepository

    repo = BrainConversationRepository(db)
    conversation = await repo.get_by_id(conversation_id)
    if conversation is None or conversation.brain_id != brain.id:
        from app.exceptions import NotFoundError

        raise NotFoundError(f"Conversation {conversation_id} not found")
    return _conversation_to_read(conversation)


@router.post(
    "/{business_id}/brain/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    brain: Annotated[BusinessBrain, Depends(require_brain_modify)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SendMessageResponse:
    """Send a message from the business owner to the Brain.

    The Brain will process the message and respond. If the Brain
    identifies a business knowledge proposal from the conversation,
    it will be created as a pending proposal.
    """
    service = _get_brain_conversation_service(db)
    owner_msg, brain_msg = await service.send_owner_message(
        conversation_id, body.content
    )
    return SendMessageResponse(
        owner_message=_message_to_read(owner_msg),
        brain_message=_message_to_read(brain_msg),
    )


@router.post(
    "/{business_id}/brain/conversations/{conversation_id}/archive",
    response_model=BrainConversationRead,
)
async def archive_conversation(
    conversation_id: uuid.UUID,
    brain: Annotated[BusinessBrain, Depends(require_brain_modify)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrainConversationRead:
    """Archive a conversation."""
    service = _get_brain_conversation_service(db)
    conversation = await service.archive_conversation(conversation_id)
    return BrainConversationRead.model_validate(conversation)


# ---------------------------------------------------------------------------
# Proposal Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/brain/proposals",
    response_model=list[BrainProposalRead],
)
async def list_proposals(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[BrainProposalRead]:
    """List all proposals for this Brain."""
    service = _get_brain_conversation_service(db)
    proposals = await service.list_proposals(brain.id)
    return [_proposal_to_read(p) for p in proposals]


@router.get(
    "/{business_id}/brain/proposals/pending",
    response_model=list[BrainProposalRead],
)
async def list_pending_proposals(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[BrainProposalRead]:
    """List pending proposals awaiting owner decision."""
    service = _get_brain_conversation_service(db)
    proposals = await service.list_pending_proposals(brain.id)
    return [_proposal_to_read(p) for p in proposals]


@router.post(
    "/{business_id}/brain/proposals/{proposal_id}/approve",
    response_model=BrainProposalRead,
)
async def approve_proposal(
    proposal_id: uuid.UUID,
    brain: Annotated[BusinessBrain, Depends(require_brain_approve)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    body: ApproveProposalRequest | None = None,
) -> BrainProposalRead:
    """Approve a Brain proposal.

    Optionally provide edited_change to approve with modifications.
    The approved proposal becomes eligible for application to the
    governed Brain state.
    """
    service = _get_brain_conversation_service(db)
    edited_change = body.edited_change if body else None
    proposal = await service.approve_proposal(proposal_id, edited_change)
    return _proposal_to_read(proposal)


@router.post(
    "/{business_id}/brain/proposals/{proposal_id}/reject",
    response_model=BrainProposalRead,
)
async def reject_proposal(
    proposal_id: uuid.UUID,
    brain: Annotated[BusinessBrain, Depends(require_brain_approve)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrainProposalRead:
    """Reject a Brain proposal."""
    service = _get_brain_conversation_service(db)
    proposal = await service.reject_proposal(proposal_id)
    return _proposal_to_read(proposal)


# ---------------------------------------------------------------------------
# Knowledge & Attention Endpoints
# ---------------------------------------------------------------------------


class KnowledgeSummaryResponse(BaseModel):
    """Summary of Brain knowledge state."""

    known: list[dict]
    proposed: list[dict]
    rejected: list[dict]
    active_config_areas: list[str]
    missing_areas: list[str]
    has_active_version: bool


class NeedsAttentionItem(BaseModel):
    """An item requiring owner attention."""

    type: str
    id: str | None = None
    title: str
    affected_area: str | None = None
    is_urgent: bool = False
    confidence: float | None = None
    proposal_type: str | None = None


class BrainContextResponse(BaseModel):
    """Full Brain context for the owner."""

    knowledge: KnowledgeSummaryResponse
    attention: list[NeedsAttentionItem]
    active_config_summary: str


@router.get(
    "/{business_id}/brain/knowledge",
    response_model=KnowledgeSummaryResponse,
)
async def get_knowledge_summary(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> KnowledgeSummaryResponse:
    """Get the Brain knowledge summary.

    Returns known (approved), proposed (pending), rejected knowledge,
    active configuration areas, and missing areas.
    """
    service = _get_brain_conversation_service(db)
    summary = await service.get_brain_knowledge_summary(
        brain.id, brain.business_id
    )
    return KnowledgeSummaryResponse(**summary)


@router.get(
    "/{business_id}/brain/needs-attention",
    response_model=list[NeedsAttentionItem],
)
async def get_needs_attention(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[NeedsAttentionItem]:
    """Get items requiring owner attention.

    Includes pending proposals, missing critical configuration,
    and other Brain signals.
    """
    service = _get_brain_conversation_service(db)
    items = await service.get_needs_attention(brain.id)
    return [NeedsAttentionItem(**item) for item in items]


@router.get(
    "/{business_id}/brain/context",
    response_model=BrainContextResponse,
)
async def get_brain_context(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrainContextResponse:
    """Get full Brain context for the owner.

    Combines knowledge summary, needs attention, and active config
    into a single response for the Brain dashboard.
    """
    service = _get_brain_conversation_service(db)
    knowledge = await service.get_brain_knowledge_summary(
        brain.id, brain.business_id
    )
    attention = await service.get_needs_attention(brain.id)
    active_config = await service._build_active_config_text(brain.id)

    return BrainContextResponse(
        knowledge=KnowledgeSummaryResponse(**knowledge),
        attention=[NeedsAttentionItem(**item) for item in attention],
        active_config_summary=active_config,
    )
