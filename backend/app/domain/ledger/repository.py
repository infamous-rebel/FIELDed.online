"""Service Ledger domain repository.

Provides database access for ServiceLedgerEntry entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.ledger.models import ServiceLedgerEntry


class LedgerRepository:
    """Data access for ServiceLedgerEntry entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, entry_id: uuid.UUID) -> ServiceLedgerEntry | None:
        """Fetch a ledger entry by ID."""
        result = await self.session.execute(
            select(ServiceLedgerEntry)
            .where(
                ServiceLedgerEntry.id == entry_id,
                ServiceLedgerEntry.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceLedgerEntry.service_execution),
                selectinload(ServiceLedgerEntry.invoice),
                selectinload(ServiceLedgerEntry.service_offer),
            )
        )
        return result.scalar_one_or_none()

    async def get_primary_by_execution(
        self, service_execution_id: uuid.UUID
    ) -> ServiceLedgerEntry | None:
        """Fetch the primary ledger entry for a service execution."""
        result = await self.session.execute(
            select(ServiceLedgerEntry)
            .where(
                ServiceLedgerEntry.service_execution_id == service_execution_id,
                ServiceLedgerEntry.is_primary.is_(True),
                ServiceLedgerEntry.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        service_offer_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceLedgerEntry]:
        """Fetch ledger entries for a business with filters."""
        stmt = (
            select(ServiceLedgerEntry)
            .where(
                ServiceLedgerEntry.business_id == business_id,
                ServiceLedgerEntry.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceLedgerEntry.service_execution),
                selectinload(ServiceLedgerEntry.invoice),
                selectinload(ServiceLedgerEntry.service_offer),
                selectinload(ServiceLedgerEntry.customer),
            )
            .order_by(ServiceLedgerEntry.completion_date.desc())
            .limit(limit)
            .offset(offset)
        )
        if payment_status is not None:
            stmt = stmt.where(ServiceLedgerEntry.payment_status == payment_status)
        if service_offer_id is not None:
            stmt = stmt.where(ServiceLedgerEntry.service_offer_id == service_offer_id)
        if customer_id is not None:
            stmt = stmt.where(ServiceLedgerEntry.customer_id == customer_id)
        if date_from is not None:
            stmt = stmt.where(ServiceLedgerEntry.completion_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(ServiceLedgerEntry.completion_date <= date_to)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(
        self,
        business_id: uuid.UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        """Calculate ledger summary/totals for a business."""
        stmt = (
            select(
                func.count().label("total_entries"),
                func.coalesce(func.sum(ServiceLedgerEntry.gross_amount), 0).label("total_gross"),
                func.coalesce(func.sum(ServiceLedgerEntry.discount), 0).label("total_discount"),
                func.coalesce(func.sum(ServiceLedgerEntry.tax), 0).label("total_tax"),
                func.coalesce(func.sum(ServiceLedgerEntry.net_amount), 0).label("total_net"),
            )
            .where(
                ServiceLedgerEntry.business_id == business_id,
                ServiceLedgerEntry.is_primary.is_(True),
                ServiceLedgerEntry.deleted_at.is_(None),
            )
        )
        if date_from is not None:
            stmt = stmt.where(ServiceLedgerEntry.completion_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(ServiceLedgerEntry.completion_date <= date_to)

        result = await self.session.execute(stmt)
        row = result.one()

        # Calculate paid/outstanding by payment status
        paid_stmt = (
            select(
                func.coalesce(func.sum(ServiceLedgerEntry.net_amount), 0).label("paid"),
            )
            .where(
                ServiceLedgerEntry.business_id == business_id,
                ServiceLedgerEntry.is_primary.is_(True),
                ServiceLedgerEntry.payment_status == "paid",
                ServiceLedgerEntry.deleted_at.is_(None),
            )
        )
        if date_from is not None:
            paid_stmt = paid_stmt.where(ServiceLedgerEntry.completion_date >= date_from)
        if date_to is not None:
            paid_stmt = paid_stmt.where(ServiceLedgerEntry.completion_date <= date_to)

        paid_result = await self.session.execute(paid_stmt)
        paid = paid_result.scalar_one()

        total_net = Decimal(str(row.total_net))
        paid_amount = Decimal(str(paid))
        outstanding = total_net - paid_amount

        return {
            "total_entries": row.total_entries,
            "total_gross": str(row.total_gross),
            "total_discount": str(row.total_discount),
            "total_tax": str(row.total_tax),
            "total_net": str(row.total_net),
            "paid_amount": str(paid_amount),
            "outstanding_amount": str(outstanding),
        }

    async def create(self, entry: ServiceLedgerEntry) -> ServiceLedgerEntry:
        """Persist a new ledger entry."""
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update(self, entry: ServiceLedgerEntry) -> ServiceLedgerEntry:
        """Update an existing ledger entry."""
        await self.session.flush()
        return entry
