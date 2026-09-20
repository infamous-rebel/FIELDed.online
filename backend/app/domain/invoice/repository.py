"""Invoice domain repository.

Provides database access for Invoice and InvoiceLineItem entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.invoice.models import Invoice


class InvoiceRepository:
    """Data access for Invoice entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, invoice_id: uuid.UUID) -> Invoice | None:
        """Fetch an invoice by ID with line items."""
        result = await self.session.execute(
            select(Invoice)
            .where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.service_execution),
                selectinload(Invoice.booking),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_service_execution_id(self, service_execution_id: uuid.UUID) -> Invoice | None:
        """Fetch an invoice by its service execution ID."""
        result = await self.session.execute(
            select(Invoice)
            .where(
                Invoice.service_execution_id == service_execution_id,
                Invoice.deleted_at.is_(None),
            )
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.service_execution),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        """Fetch invoices for a business."""
        stmt = (
            select(Invoice)
            .where(
                Invoice.business_id == business_id,
                Invoice.deleted_at.is_(None),
            )
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.service_execution),
            )
            .order_by(Invoice.issue_date.desc())
            .limit(limit)
            .offset(offset)
        )
        if payment_status is not None:
            stmt = stmt.where(Invoice.payment_status == payment_status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        """Fetch invoices for a customer."""
        stmt = (
            select(Invoice)
            .where(
                Invoice.customer_id == customer_id,
                Invoice.deleted_at.is_(None),
            )
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.service_execution),
            )
            .order_by(Invoice.issue_date.desc())
            .limit(limit)
            .offset(offset)
        )
        if payment_status is not None:
            stmt = stmt.where(Invoice.payment_status == payment_status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_invoice_number(self, business_id: uuid.UUID) -> str:
        """Generate the next sequential invoice number for a business.

        Format: INV-{business_short}-{sequence}
        Uses the count of existing invoices to determine the sequence.
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(Invoice)
            .where(
                Invoice.business_id == business_id,
                Invoice.deleted_at.is_(None),
            )
        )
        count = result.scalar_one()
        # Use business ID prefix for readability
        biz_prefix = str(business_id).replace("-", "")[:6].upper()
        return f"INV-{biz_prefix}-{count + 1:04d}"

    async def create(self, invoice: Invoice) -> Invoice:
        """Persist a new invoice."""
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def update(self, invoice: Invoice) -> Invoice:
        """Update an existing invoice."""
        await self.session.flush()
        return invoice

    async def count_by_business(self, business_id: uuid.UUID) -> int:
        """Count invoices for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Invoice)
            .where(
                Invoice.business_id == business_id,
                Invoice.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
