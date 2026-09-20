"""Service Ledger API endpoints.

Provides ledger listing, summaries, CSV/PDF export, and adjustments.

All ownership is verified server-side.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity.models import User
from app.domain.ledger.schemas import (
    LedgerAdjustmentRequest,
    LedgerEntryRead,
    LedgerSummaryRead,
)
from app.domain.ledger.service import LedgerService
from app.security.authorization import get_current_user, require_business_member

router = APIRouter()


def _entry_to_read(entry) -> LedgerEntryRead:
    """Convert a ServiceLedgerEntry model to the read schema."""
    return LedgerEntryRead.model_validate(entry)


# --- Business endpoints ---


@router.get(
    "/{business_id}/ledger",
    response_model=list[LedgerEntryRead],
)
async def list_ledger_entries(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    payment_status: str | None = Query(None),
    service_offer_id: uuid.UUID | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[LedgerEntryRead]:
    """List ledger entries for a business with filters."""
    service = LedgerService(db)
    entries = await service.list_entries(
        business_id,
        payment_status=payment_status,
        service_offer_id=service_offer_id,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [_entry_to_read(e) for e in entries]


@router.get(
    "/{business_id}/ledger/summary",
    response_model=LedgerSummaryRead,
)
async def get_ledger_summary(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> LedgerSummaryRead:
    """Get ledger summary/totals for a business."""
    service = LedgerService(db)
    summary = await service.get_summary(
        business_id, date_from=date_from, date_to=date_to
    )
    return LedgerSummaryRead(**summary)


@router.get(
    "/{business_id}/ledger/{entry_id}",
    response_model=LedgerEntryRead,
)
async def get_ledger_entry(
    business_id: uuid.UUID,
    entry_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> LedgerEntryRead:
    """Get a specific ledger entry."""
    service = LedgerService(db)
    entry = await service.get_business_entry(entry_id, business_id)
    return _entry_to_read(entry)


@router.get(
    "/{business_id}/ledger/export/csv",
    response_class=Response,
)
async def export_ledger_csv(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    payment_status: str | None = Query(None),
    service_offer_id: uuid.UUID | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> Response:
    """Export ledger as CSV."""
    service = LedgerService(db)
    csv_content = await service.export_csv(
        business_id,
        payment_status=payment_status,
        service_offer_id=service_offer_id,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
    )

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="ledger-{business_id}.csv"',
        },
    )


@router.get(
    "/{business_id}/ledger/export/pdf",
    response_class=Response,
)
async def export_ledger_pdf(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    payment_status: str | None = Query(None),
    service_offer_id: uuid.UUID | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> Response:
    """Export ledger as PDF report."""
    service = LedgerService(db)
    pdf_bytes = await service.export_pdf(
        business_id,
        payment_status=payment_status,
        service_offer_id=service_offer_id,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ledger-{business_id}.pdf"',
        },
    )


@router.post(
    "/{business_id}/ledger/adjustments",
    response_model=LedgerEntryRead,
    status_code=201,
)
async def create_ledger_adjustment(
    business_id: uuid.UUID,
    original_entry_id: uuid.UUID,
    body: LedgerAdjustmentRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> LedgerEntryRead:
    """Create a ledger adjustment/reversal.

    Uses append-oriented mechanism — the original entry is not modified.
    """
    service = LedgerService(db)
    adjustment = await service.create_adjustment(
        business_id=business_id,
        original_entry_id=original_entry_id,
        adjustment_gross=body.adjustment_gross,
        adjustment_discount=body.adjustment_discount,
        adjustment_tax=body.adjustment_tax,
        adjustment_net=body.adjustment_net,
        currency=body.currency,
        notes=body.notes,
        actor_id=user.id,
    )
    await db.refresh(adjustment)
    return _entry_to_read(adjustment)
