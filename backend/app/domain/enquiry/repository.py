"""Enquiry domain repository.

Provides database access for Enquiry, Conversation, and Message entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enquiry.models import Conversation, Enquiry, Message


class EnquiryRepository:
    """Data access for Enquiry entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, enquiry_id: uuid.UUID) -> Enquiry | None:
        """Fetch an enquiry by ID."""
        result = await self.session.execute(
            select(Enquiry)
            .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))
            .options(
                selectinload(Enquiry.conversation),
                selectinload(Enquiry.service_offer),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(
        self, enquiry_id: uuid.UUID
    ) -> Enquiry | None:
        """Fetch an enquiry with all relationships loaded."""
        result = await self.session.execute(
            select(Enquiry)
            .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))
            .options(
                selectinload(Enquiry.conversation),
                selectinload(Enquiry.service_offer),
                selectinload(Enquiry.business),
                selectinload(Enquiry.customer),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Enquiry]:
        """Fetch enquiries for a customer."""
        stmt = (
            select(Enquiry)
            .where(
                Enquiry.customer_id == customer_id,
                Enquiry.deleted_at.is_(None),
            )
            .options(selectinload(Enquiry.service_offer))
            .order_by(Enquiry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Enquiry.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Enquiry]:
        """Fetch enquiries for a business."""
        stmt = (
            select(Enquiry)
            .where(
                Enquiry.business_id == business_id,
                Enquiry.deleted_at.is_(None),
            )
            .options(
                selectinload(Enquiry.service_offer),
                selectinload(Enquiry.customer),
            )
            .order_by(Enquiry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Enquiry.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_customer(
        self, customer_id: uuid.UUID
    ) -> int:
        """Count enquiries for a customer."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Enquiry)
            .where(
                Enquiry.customer_id == customer_id,
                Enquiry.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_by_business(
        self, business_id: uuid.UUID
    ) -> int:
        """Count enquiries for a business."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Enquiry)
            .where(
                Enquiry.business_id == business_id,
                Enquiry.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def create(self, enquiry: Enquiry) -> Enquiry:
        """Persist a new enquiry."""
        self.session.add(enquiry)
        await self.session.flush()
        return enquiry

    async def update(self, enquiry: Enquiry) -> Enquiry:
        """Update an existing enquiry."""
        await self.session.flush()
        return enquiry


class ConversationRepository:
    """Data access for Conversation entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_enquiry_id(
        self, enquiry_id: uuid.UUID
    ) -> Conversation | None:
        """Fetch the conversation for an enquiry."""
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.enquiry_id == enquiry_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Fetch a conversation by ID."""
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation."""
        self.session.add(conversation)
        await self.session.flush()
        return conversation


class MessageRepository:
    """Data access for Message entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """Fetch messages for a conversation (oldest first)."""
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_id(self, message_id: uuid.UUID) -> Message | None:
        """Fetch a message by ID."""
        result = await self.session.execute(
            select(Message)
            .where(
                Message.id == message_id,
                Message.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, message: Message) -> Message:
        """Persist a new message."""
        self.session.add(message)
        await self.session.flush()
        return message

    async def update(self, message: Message) -> Message:
        """Update an existing message."""
        await self.session.flush()
        return message
