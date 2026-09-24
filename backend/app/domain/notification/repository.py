"""Notification domain repository.

Provides database access for Notification entities.
All queries enforce soft-delete filtering and tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notification.models import Notification


class NotificationRepository:
    """Data access for Notification entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, notification: Notification) -> Notification:
        """Persist a new notification."""
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def get_by_id(self, notification_id: uuid.UUID, *, business_id: uuid.UUID) -> Notification | None:
        """Fetch a notification by ID (tenant-scoped)."""
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.business_id == business_id,
                Notification.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Notification | None:
        """Fetch a notification by idempotency key."""
        result = await self.session.execute(
            select(Notification).where(
                Notification.idempotency_key == idempotency_key,
                Notification.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        notification_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a business (tenant-scoped)."""
        stmt = (
            select(Notification)
            .where(
                Notification.business_id == business_id,
                Notification.deleted_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if notification_type:
            stmt = stmt.where(Notification.notification_type == notification_type)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_customer(
        self,
        customer_id: uuid.UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a customer."""
        stmt = (
            select(Notification)
            .where(
                Notification.customer_id == customer_id,
                Notification.deleted_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_unread(self, customer_id: uuid.UUID) -> int:
        """Count unread notifications for a customer."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.customer_id == customer_id,
                Notification.read_at.is_(None),
                Notification.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def mark_read(self, notification_id: uuid.UUID, *, customer_id: uuid.UUID) -> Notification | None:
        """Mark a notification as read."""
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.customer_id == customer_id,
                Notification.deleted_at.is_(None),
            )
        )
        notification = result.scalar_one_or_none()
        if notification and notification.read_at is None:
            notification.read_at = datetime.utcnow()
            await self.session.flush()
        return notification
