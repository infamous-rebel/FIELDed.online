"""Quote API endpoints.

Provides quote creation (business), listing, retrieval,
acceptance/decline (customer), and lifecycle transitions.

All ownership is verified server-side.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.common.enums import QuoteStatus
from app.domain.identity.models import User
from app.domain.quote.schemas import (
    QuoteCreate,
    QuoteRead,
    QuoteTransitionRequest,
)
from app.domain.quote.service import QuoteService
from app.security.authorization import require_business_member, require_customer

router = APIRouter()


def _quote_to_read(quote) -> QuoteRead:
    """Convert a Quote model to the read schema."""
    return QuoteRead.model_validate(quote)


# --- Business endpoints (create/issue quotes) ---


@router.post(
    "/{business_id}/quotes",
    response_model=QuoteRead,
    status_code=201,
)
async def create_quote(
    business_id: uuid.UUID,
    body: QuoteCreate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuoteRead:
    """Create a quote for an enquiry (business action).

    The pricing is calculated deterministically from the
    ServiceOffer and active Brain pricing rules.
    """
    service = QuoteService(db)

    quote = await service.create_quote(
        business_id=business_id,
        enquiry_id=body.enquiry_id,
        notes=body.notes,
    )

    await db.refresh(quote)
    return _quote_to_read(quote)


@router.get(
    "/{business_id}/quotes",
    response_model=list[QuoteRead],
)
async def list_business_quotes(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[QuoteRead]:
    """List quotes for a business."""
    service = QuoteService(db)
    quotes = await service.list_business_quotes(
        business_id, status=status, limit=limit, offset=offset
    )
    return [_quote_to_read(q) for q in quotes]


@router.get(
    "/{business_id}/quotes/{quote_id}",
    response_model=QuoteRead,
)
async def get_business_quote(
    business_id: uuid.UUID,
    quote_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuoteRead:
    """Get a specific quote for a business."""
    service = QuoteService(db)
    quote = await service.get_business_quote(quote_id, business_id)
    return _quote_to_read(quote)


@router.post(
    "/{business_id}/quotes/{quote_id}/transition",
    response_model=QuoteRead,
)
async def transition_business_quote(
    business_id: uuid.UUID,
    quote_id: uuid.UUID,
    body: QuoteTransitionRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuoteRead:
    """Transition a quote (business: issue or expire)."""
    service = QuoteService(db)
    quote = await service.get_business_quote(quote_id, business_id)
    target_status = QuoteStatus(body.target_status)
    quote = await service.transition_quote(quote, target_status, actor="business")
    await db.refresh(quote)
    return _quote_to_read(quote)


# --- Customer endpoints (view/accept/decline quotes) ---


@router.get("/my-quotes", response_model=list[QuoteRead])
async def list_my_quotes(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[QuoteRead]:
    """List all quotes for the authenticated customer."""
    service = QuoteService(db)
    quotes = await service.list_customer_quotes(user.id, status=status, limit=limit, offset=offset)
    return [_quote_to_read(q) for q in quotes]


@router.get("/my-quotes/{quote_id}", response_model=QuoteRead)
async def get_my_quote(
    quote_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuoteRead:
    """Get a specific quote owned by the authenticated customer."""
    service = QuoteService(db)
    quote = await service.get_customer_quote(quote_id, user.id)
    return _quote_to_read(quote)


@router.post("/my-quotes/{quote_id}/transition", response_model=QuoteRead)
async def transition_my_quote(
    quote_id: uuid.UUID,
    body: QuoteTransitionRequest,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuoteRead:
    """Transition a quote (customer: accept or decline)."""
    service = QuoteService(db)
    quote = await service.get_customer_quote(quote_id, user.id)
    target_status = QuoteStatus(body.target_status)
    quote = await service.transition_quote(quote, target_status, actor="customer")
    await db.refresh(quote)
    return _quote_to_read(quote)
