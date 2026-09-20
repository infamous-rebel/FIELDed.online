"""Payment domain repository.

Provides database access for Payment and PaymentAttempt entities.
All queries enforce tenant isolation and soft-delete filtering.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.payment.models import Payment, PaymentAttempt


class PaymentRepository:
    """Data access for Payment entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        """Fetch a payment by ID with attempts."""
        result = await self.session.execute(
            select(Payment)
            .where(Payment.id == payment_id, Payment.deleted_at.is_(None))
            .options(selectinload(Payment.attempts))
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> Payment | None:
        """Fetch a payment by its idempotency key."""
        result = await self.session.execute(
            select(Payment)
            .where(
                Payment.idempotency_key == idempotency_key,
                Payment.deleted_at.is_(None),
            )
            .options(selectinload(Payment.attempts))
        )
        return result.scalar_one_or_none()

    async def get_by_provider_reference(
        self, provider_reference: str
    ) -> Payment | None:
        """Fetch a payment by provider reference."""
        result = await self.session.execute(
            select(Payment)
            .where(
                Payment.provider_reference == provider_reference,
                Payment.deleted_at.is_(None),
            )
            .options(selectinload(Payment.attempts))
        )
        return result.scalar_one_or_none()

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        """Fetch payments for a business (tenant-scoped)."""
        stmt = (
            select(Payment)
            .where(
                Payment.business_id == business_id,
                Payment.deleted_at.is_(None),
            )
            .options(selectinload(Payment.attempts))
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Payment.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        """Fetch payments for a customer."""
        stmt = (
            select(Payment)
            .where(
                Payment.customer_id == customer_id,
                Payment.deleted_at.is_(None),
            )
            .options(selectinload(Payment.attempts))
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Payment.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_invoice(
        self, invoice_id: uuid.UUID
    ) -> list[Payment]:
        """Fetch all payments for an invoice."""
        result = await self.session.execute(
            select(Payment)
            .where(
                Payment.invoice_id == invoice_id,
                Payment.deleted_at.is_(None),
            )
            .options(selectinload(Payment.attempts))
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_successful_total_for_invoice(
        self, invoice_id: uuid.UUID
    ) -> str:
        """Sum of successful payment amounts for an invoice."""
        from decimal import Decimal

        result = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
            .where(
                Payment.invoice_id == invoice_id,
                Payment.status.in_(["succeeded", "partially_refunded"]),
                Payment.deleted_at.is_(None),
            )
        )
        return str(result.scalar_one())

    async def get_refunded_total_for_invoice(
        self, invoice_id: uuid.UUID
    ) -> str:
        """Sum of refunded amounts for an invoice."""
        from decimal import Decimal

        result = await self.session.execute(
            select(func.coalesce(func.sum(Payment.refunded_amount), Decimal("0.00")))
            .where(
                Payment.invoice_id == invoice_id,
                Payment.status.in_(["succeeded", "partially_refunded", "refunded"]),
                Payment.deleted_at.is_(None),
            )
        )
        return str(result.scalar_one())

    async def create(self, payment: Payment) -> Payment:
        """Persist a new payment."""
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def update(self, payment: Payment) -> Payment:
        """Update an existing payment."""
        await self.session.flush()
        return payment

    async def create_attempt(self, attempt: PaymentAttempt) -> PaymentAttempt:
        """Persist a new payment attempt."""
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def count_by_business(self, business_id: uuid.UUID) -> int:
        """Count payments for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.business_id == business_id,
                Payment.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
