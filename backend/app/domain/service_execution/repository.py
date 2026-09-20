"""Service Execution domain repository.

Provides database access for ServiceExecution entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.service_execution.models import ServiceExecution


class ServiceExecutionRepository:
    """Data access for ServiceExecution entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, execution_id: uuid.UUID) -> ServiceExecution | None:
        """Fetch a service execution by ID."""
        result = await self.session.execute(
            select(ServiceExecution)
            .where(
                ServiceExecution.id == execution_id,
                ServiceExecution.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceExecution.booking),
                selectinload(ServiceExecution.service_offer),
                selectinload(ServiceExecution.customer),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_booking_id(self, booking_id: uuid.UUID) -> ServiceExecution | None:
        """Fetch a service execution by booking ID."""
        result = await self.session.execute(
            select(ServiceExecution)
            .where(
                ServiceExecution.booking_id == booking_id,
                ServiceExecution.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceExecution.booking),
                selectinload(ServiceExecution.service_offer),
                selectinload(ServiceExecution.customer),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceExecution]:
        """Fetch service executions for a business."""
        stmt = (
            select(ServiceExecution)
            .where(
                ServiceExecution.business_id == business_id,
                ServiceExecution.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceExecution.booking),
                selectinload(ServiceExecution.service_offer),
                selectinload(ServiceExecution.customer),
            )
            .order_by(ServiceExecution.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(ServiceExecution.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceExecution]:
        """Fetch service executions for a customer."""
        stmt = (
            select(ServiceExecution)
            .where(
                ServiceExecution.customer_id == customer_id,
                ServiceExecution.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceExecution.booking),
                selectinload(ServiceExecution.service_offer),
            )
            .order_by(ServiceExecution.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(ServiceExecution.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, execution: ServiceExecution) -> ServiceExecution:
        """Persist a new service execution."""
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def update(self, execution: ServiceExecution) -> ServiceExecution:
        """Update an existing service execution."""
        await self.session.flush()
        return execution

    async def count_by_business(self, business_id: uuid.UUID) -> int:
        """Count service executions for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(ServiceExecution)
            .where(
                ServiceExecution.business_id == business_id,
                ServiceExecution.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_completed_by_business(self, business_id: uuid.UUID) -> int:
        """Count completed service executions for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(ServiceExecution)
            .where(
                ServiceExecution.business_id == business_id,
                ServiceExecution.status == "completed",
                ServiceExecution.deleted_at.is_(None),
            )
        )
        return result.scalar_one()
