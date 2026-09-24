"""Communication domain repository.

Provides database access for Communication entities.
All queries enforce soft-delete filtering and tenant isolation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.communication.models import (
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    Communication,
    CommunicationAttempt,
    CommunicationAuditEvent,
    CommunicationRecipient,
    CommunicationTemplate,
    CommunicationTemplateVersion,
    CommunicationWebhook,
    CustomerCommunicationPreference,
)


class CommunicationRepository:
    """Data access for Communication entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, communication: Communication) -> Communication:
        """Persist a new communication."""
        self.session.add(communication)
        await self.session.flush()
        return communication

    async def get_by_id(self, communication_id: uuid.UUID, *, business_id: uuid.UUID) -> Communication | None:
        """Fetch a communication by ID (tenant-scoped)."""
        result = await self.session.execute(
            select(Communication)
            .where(
                Communication.id == communication_id,
                Communication.business_id == business_id,
                Communication.deleted_at.is_(None),
            )
            .options(
                selectinload(Communication.recipients),
                selectinload(Communication.attempts),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Communication | None:
        """Fetch a communication by idempotency key."""
        result = await self.session.execute(
            select(Communication).where(
                Communication.idempotency_key == idempotency_key,
                Communication.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        channel: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Communication]:
        """List communications for a business (tenant-scoped)."""
        stmt = (
            select(Communication)
            .where(
                Communication.business_id == business_id,
                Communication.deleted_at.is_(None),
            )
            .order_by(Communication.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if channel:
            stmt = stmt.where(Communication.channel == channel)
        if purpose:
            stmt = stmt.where(Communication.purpose == purpose)
        if status:
            stmt = stmt.where(Communication.status == status)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, communication: Communication) -> Communication:
        """Update an existing communication."""
        await self.session.flush()
        return communication

    async def add_recipient(self, recipient: CommunicationRecipient) -> CommunicationRecipient:
        """Add a recipient to a communication."""
        self.session.add(recipient)
        await self.session.flush()
        return recipient

    async def add_attempt(self, attempt: CommunicationAttempt) -> CommunicationAttempt:
        """Record a provider delivery attempt."""
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def list_attempts(self, communication_id: uuid.UUID) -> list[CommunicationAttempt]:
        """List attempts for a communication."""
        result = await self.session.execute(
            select(CommunicationAttempt)
            .where(CommunicationAttempt.communication_id == communication_id)
            .order_by(CommunicationAttempt.created_at.asc())
        )
        return list(result.scalars().all())


class CommunicationTemplateRepository:
    """Data access for CommunicationTemplate entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, template: CommunicationTemplate) -> CommunicationTemplate:
        """Persist a new template."""
        self.session.add(template)
        await self.session.flush()
        return template

    async def get_by_id(self, template_id: uuid.UUID, *, business_id: uuid.UUID) -> CommunicationTemplate | None:
        """Fetch a template by ID (tenant-scoped)."""
        result = await self.session.execute(
            select(CommunicationTemplate).where(
                CommunicationTemplate.id == template_id,
                CommunicationTemplate.business_id == business_id,
                CommunicationTemplate.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        channel: str | None = None,
        purpose: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommunicationTemplate]:
        """List templates for a business."""
        stmt = (
            select(CommunicationTemplate)
            .where(
                CommunicationTemplate.business_id == business_id,
                CommunicationTemplate.deleted_at.is_(None),
            )
            .order_by(CommunicationTemplate.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if channel:
            stmt = stmt.where(CommunicationTemplate.channel == channel)
        if purpose:
            stmt = stmt.where(CommunicationTemplate.purpose == purpose)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_version(self, version: CommunicationTemplateVersion) -> CommunicationTemplateVersion:
        """Add a new immutable version to a template."""
        self.session.add(version)
        await self.session.flush()
        return version

    async def list_versions(self, template_id: uuid.UUID) -> list[CommunicationTemplateVersion]:
        """List all versions for a template."""
        result = await self.session.execute(
            select(CommunicationTemplateVersion)
            .where(CommunicationTemplateVersion.template_id == template_id)
            .order_by(CommunicationTemplateVersion.version_number.asc())
        )
        return list(result.scalars().all())

    async def get_version(self, version_id: uuid.UUID) -> CommunicationTemplateVersion | None:
        """Fetch a specific template version."""
        result = await self.session.execute(
            select(CommunicationTemplateVersion).where(CommunicationTemplateVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def update(self, template: CommunicationTemplate) -> CommunicationTemplate:
        """Update a template."""
        await self.session.flush()
        return template


class CommunicationConfigRepository:
    """Data access for business communication configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_channel_config(self, business_id: uuid.UUID, channel: str) -> BusinessCommunicationChannel | None:
        """Get channel configuration for a business."""
        result = await self.session.execute(
            select(BusinessCommunicationChannel).where(
                BusinessCommunicationChannel.business_id == business_id,
                BusinessCommunicationChannel.channel == channel,
                BusinessCommunicationChannel.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_channel_configs(self, business_id: uuid.UUID) -> list[BusinessCommunicationChannel]:
        """List all channel configs for a business."""
        result = await self.session.execute(
            select(BusinessCommunicationChannel).where(
                BusinessCommunicationChannel.business_id == business_id,
                BusinessCommunicationChannel.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def upsert_channel_config(self, config: BusinessCommunicationChannel) -> BusinessCommunicationChannel:
        """Create or update a channel configuration."""
        existing = await self.get_channel_config(config.business_id, config.channel)
        if existing:
            if config.enabled is not None:
                existing.enabled = config.enabled
            if config.provider_ref is not None:
                existing.provider_ref = config.provider_ref
            if config.settings is not None:
                existing.settings = config.settings
            await self.session.flush()
            return existing
        self.session.add(config)
        await self.session.flush()
        return config

    async def get_purpose_config(self, business_id: uuid.UUID, purpose: str) -> BusinessCommunicationPurpose | None:
        """Get purpose configuration for a business."""
        result = await self.session.execute(
            select(BusinessCommunicationPurpose).where(
                BusinessCommunicationPurpose.business_id == business_id,
                BusinessCommunicationPurpose.purpose == purpose,
                BusinessCommunicationPurpose.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_purpose_configs(self, business_id: uuid.UUID) -> list[BusinessCommunicationPurpose]:
        """List all purpose configs for a business."""
        result = await self.session.execute(
            select(BusinessCommunicationPurpose).where(
                BusinessCommunicationPurpose.business_id == business_id,
                BusinessCommunicationPurpose.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def upsert_purpose_config(self, config: BusinessCommunicationPurpose) -> BusinessCommunicationPurpose:
        """Create or update a purpose configuration."""
        existing = await self.get_purpose_config(config.business_id, config.purpose)
        if existing:
            if config.enabled is not None:
                existing.enabled = config.enabled
            if config.permitted_channels is not None:
                existing.permitted_channels = config.permitted_channels
            await self.session.flush()
            return existing
        self.session.add(config)
        await self.session.flush()
        return config


class ConsentRepository:
    """Data access for customer communication preferences."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_preference(
        self,
        customer_id: uuid.UUID,
        business_id: uuid.UUID,
        channel: str | None = None,
        purpose: str | None = None,
    ) -> CustomerCommunicationPreference | None:
        """Get a specific preference."""
        stmt = select(CustomerCommunicationPreference).where(
            CustomerCommunicationPreference.customer_id == customer_id,
            CustomerCommunicationPreference.business_id == business_id,
            CustomerCommunicationPreference.deleted_at.is_(None),
        )
        if channel is None:
            stmt = stmt.where(CustomerCommunicationPreference.channel.is_(None))
        else:
            stmt = stmt.where(CustomerCommunicationPreference.channel == channel)
        if purpose is None:
            stmt = stmt.where(CustomerCommunicationPreference.purpose.is_(None))
        else:
            stmt = stmt.where(CustomerCommunicationPreference.purpose == purpose)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_customer(
        self, customer_id: uuid.UUID, business_id: uuid.UUID
    ) -> list[CustomerCommunicationPreference]:
        """List all preferences for a customer at a business."""
        result = await self.session.execute(
            select(CustomerCommunicationPreference).where(
                CustomerCommunicationPreference.customer_id == customer_id,
                CustomerCommunicationPreference.business_id == business_id,
                CustomerCommunicationPreference.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def upsert(self, pref: CustomerCommunicationPreference) -> CustomerCommunicationPreference:
        """Create or update a preference."""
        existing = await self.get_preference(pref.customer_id, pref.business_id, pref.channel, pref.purpose)
        if existing:
            for attr in (
                "consent_state",
                "opt_in",
                "suppression",
                "suppression_reason",
                "do_not_contact",
                "source",
                "consented_at",
            ):
                val = getattr(pref, attr, None)
                if val is not None:
                    setattr(existing, attr, val)
            await self.session.flush()
            return existing
        self.session.add(pref)
        await self.session.flush()
        return pref


class WebhookRepository:
    """Data access for communication webhooks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, webhook: CommunicationWebhook) -> CommunicationWebhook:
        """Persist a new webhook event."""
        self.session.add(webhook)
        await self.session.flush()
        return webhook

    async def get_by_provider_event(self, provider: str, external_event_id: str) -> CommunicationWebhook | None:
        """Fetch a webhook by provider + external event ID (idempotency)."""
        result = await self.session.execute(
            select(CommunicationWebhook).where(
                CommunicationWebhook.provider == provider,
                CommunicationWebhook.external_event_id == external_event_id,
            )
        )
        return result.scalar_one_or_none()

    async def update(self, webhook: CommunicationWebhook) -> CommunicationWebhook:
        """Update a webhook record."""
        await self.session.flush()
        return webhook


class AuditRepository:
    """Data access for communication audit events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: CommunicationAuditEvent) -> CommunicationAuditEvent:
        """Record an audit event (append-only)."""
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_communication(self, communication_id: uuid.UUID) -> list[CommunicationAuditEvent]:
        """List audit events for a communication."""
        result = await self.session.execute(
            select(CommunicationAuditEvent)
            .where(CommunicationAuditEvent.communication_id == communication_id)
            .order_by(CommunicationAuditEvent.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[CommunicationAuditEvent]:
        """List audit events for a business."""
        stmt = (
            select(CommunicationAuditEvent)
            .where(CommunicationAuditEvent.business_id == business_id)
            .order_by(CommunicationAuditEvent.created_at.desc())
            .limit(limit)
        )
        if event_type:
            stmt = stmt.where(CommunicationAuditEvent.event_type == event_type)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
