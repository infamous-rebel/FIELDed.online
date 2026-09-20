"""Invoice API endpoints.

Provides invoice retrieval, listing, PDF download, and payment status
updates.

All ownership is verified server-side.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.common.enums import InvoicePaymentStatus
from app.domain.identity.models import User
from app.domain.invoice.schemas import (
    InvoicePaymentUpdateRequest,
    InvoiceRead,
)
from app.domain.invoice.service import InvoiceService
from app.security.authorization import get_current_user, require_business_member, require_customer

router = APIRouter()


def _invoice_to_read(invoice) -> InvoiceRead:
    """Convert an Invoice model to the read schema."""
    return InvoiceRead.model_validate(invoice)


# --- Business endpoints ---


@router.get(
    "/{business_id}/invoices",
    response_model=list[InvoiceRead],
)
async def list_business_invoices(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    payment_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[InvoiceRead]:
    """List invoices for a business."""
    service = InvoiceService(db)
    invoices = await service.list_business_invoices(
        business_id, payment_status=payment_status, limit=limit, offset=offset
    )
    return [_invoice_to_read(i) for i in invoices]


@router.get(
    "/{business_id}/invoices/{invoice_id}",
    response_model=InvoiceRead,
)
async def get_business_invoice(
    business_id: uuid.UUID,
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> InvoiceRead:
    """Get a specific invoice for a business."""
    service = InvoiceService(db)
    invoice = await service.get_business_invoice(invoice_id, business_id)
    return _invoice_to_read(invoice)


@router.get(
    "/{business_id}/invoices/{invoice_id}/pdf",
    response_class=Response,
)
async def download_invoice_pdf(
    business_id: uuid.UUID,
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Download the PDF invoice document."""
    service = InvoiceService(db)
    invoice = await service.get_business_invoice(invoice_id, business_id)
    pdf_bytes = await service.generate_invoice_pdf(invoice)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="invoice-{invoice.invoice_number}.pdf"',
        },
    )


@router.patch(
    "/{business_id}/invoices/{invoice_id}/payment",
    response_model=InvoiceRead,
)
async def update_invoice_payment_status(
    business_id: uuid.UUID,
    invoice_id: uuid.UUID,
    body: InvoicePaymentUpdateRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> InvoiceRead:
    """Update the payment status of an invoice."""
    service = InvoiceService(db)
    invoice = await service.get_business_invoice(invoice_id, business_id)
    new_status = InvoicePaymentStatus(body.payment_status)
    invoice = await service.update_payment_status(
        invoice, new_status, actor_id=user.id
    )
    await db.refresh(invoice)
    return _invoice_to_read(invoice)


# --- Customer endpoints ---


@router.get(
    "/my-invoices",
    response_model=list[InvoiceRead],
)
async def list_my_invoices(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    payment_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[InvoiceRead]:
    """List invoices for the authenticated customer."""
    service = InvoiceService(db)
    invoices = await service.list_customer_invoices(
        user.id, payment_status=payment_status, limit=limit, offset=offset
    )
    return [_invoice_to_read(i) for i in invoices]


@router.get(
    "/my-invoices/{invoice_id}",
    response_model=InvoiceRead,
)
async def get_my_invoice(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> InvoiceRead:
    """Get a specific invoice for the authenticated customer."""
    service = InvoiceService(db)
    invoice = await service.get_customer_invoice(invoice_id, user.id)
    return _invoice_to_read(invoice)


@router.get(
    "/my-invoices/{invoice_id}/pdf",
    response_class=Response,
)
async def download_my_invoice_pdf(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Download the PDF invoice document (customer view)."""
    service = InvoiceService(db)
    invoice = await service.get_customer_invoice(invoice_id, user.id)
    pdf_bytes = await service.generate_invoice_pdf(invoice)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="invoice-{invoice.invoice_number}.pdf"',
        },
    )
