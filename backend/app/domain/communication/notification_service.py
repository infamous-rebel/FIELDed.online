"""Notification service.

Manages persisted notification state: creation, read/unread,
unread count, lookup, and idempotency.

Separate from the OrchestrationService which handles the full
communication pipeline.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notification.models import Notification
from app.domain.notification.repository import NotificationRepository


class NotificationService:
    """Manages notification lifecycle.

    Responsibilities:
    - Create notifications (idempotent)
    - Read/unread state
    - Unread count
    - Notification lookup
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    async def create_notification(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID | None,
        notification_type: str,
        title: str,
        body: str,
        idempotency_key: str,
        priority: str = "NORMAL",
        related_entity_type: str | None = None,
        related_entity_id: uuid.UUID | None = None,
    ) -> Notification:
        """Create a notification (idempotent by key).

        If a notification with the same idempotency_key already exists,
        returns the existing record without creating a duplicate.
        """
        # Check idempotency
        existing = await self.repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        notification = Notification(
            business_id=business_id,
            customer_id=customer_id,
            notification_type=notification_type,
            title=title,
            body=body,
            idempotency_key=idempotency_key,
            priority=priority,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        return await self.repo.create(notification)

    async def get_notification(
        self,
        notification_id: uuid.UUID,
        *,
        business_id: uuid.UUID,
    ) -> Notification | None:
        """Get a notification by ID (tenant-scoped)."""
        return await self.repo.get_by_id(notification_id, business_id=business_id)

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        notification_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a business."""
        return await self.repo.list_for_business(
            business_id,
            notification_type=notification_type,
            limit=limit,
            offset=offset,
        )

    async def list_for_customer(
        self,
        customer_id: uuid.UUID,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a customer."""
        return await self.repo.list_for_customer(
            customer_id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )

    async def count_unread(self, customer_id: uuid.UUID) -> int:
        """Count unread notifications for a customer."""
        return await self.repo.count_unread(customer_id)

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        *,
        customer_id: uuid.UUID,
    ) -> Notification | None:
        """Mark a notification as read."""
        return await self.repo.mark_read(notification_id, customer_id=customer_id)
