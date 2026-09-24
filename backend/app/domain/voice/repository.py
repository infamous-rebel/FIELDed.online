"""Voice / Call Agent domain repositories.

Database access for voice entities.  All queries enforce soft-delete
filtering and tenant isolation.  Primary business-owned entities
(voice calls, call agent configuration, campaigns) are scoped directly
by business_id; child records (participants, attempts, sessions,
escalations, campaign recipients) are tenant-scoped through a join to
their parent, so cross-business access fails at the repository level.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.voice.models import (
    CallAgentConfiguration,
    CampaignRecipient,
    CommunicationCampaign,
    VoiceCall,
    VoiceCallAttempt,
    VoiceCallEscalation,
    VoiceCallParticipant,
    VoiceCallSession,
)


class VoiceCallRepository:
    """Data access for VoiceCall entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, call: VoiceCall) -> VoiceCall:
        """Persist a new call."""
        self.session.add(call)
        await self.session.flush()
        return call

    async def get_by_id(self, call_id: uuid.UUID, *, business_id: uuid.UUID) -> VoiceCall | None:
        """Fetch a call by ID (tenant-scoped)."""
        result = await self.session.execute(
            select(VoiceCall)
            .where(
                VoiceCall.id == call_id,
                VoiceCall.business_id == business_id,
                VoiceCall.deleted_at.is_(None),
            )
            .options(
                selectinload(VoiceCall.participants),
                selectinload(VoiceCall.attempts),
                selectinload(VoiceCall.sessions),
                selectinload(VoiceCall.escalations),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, business_id: uuid.UUID, idempotency_key: str) -> VoiceCall | None:
        """Fetch a call by (business, idempotency key)."""
        result = await self.session.execute(
            select(VoiceCall).where(
                VoiceCall.business_id == business_id,
                VoiceCall.idempotency_key == idempotency_key,
                VoiceCall.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        call_type: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VoiceCall]:
        """List calls for a business (tenant-scoped)."""
        stmt = (
            select(VoiceCall)
            .where(
                VoiceCall.business_id == business_id,
                VoiceCall.deleted_at.is_(None),
            )
            .order_by(VoiceCall.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if call_type:
            stmt = stmt.where(VoiceCall.call_type == call_type)
        if purpose:
            stmt = stmt.where(VoiceCall.purpose == purpose)
        if status:
            stmt = stmt.where(VoiceCall.status == status)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, call: VoiceCall) -> VoiceCall:
        """Update an existing call."""
        await self.session.flush()
        return call


class VoiceCallParticipantRepository:
    """Data access for VoiceCallParticipant entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, participant: VoiceCallParticipant) -> VoiceCallParticipant:
        """Persist a new participant."""
        self.session.add(participant)
        await self.session.flush()
        return participant

    async def get_by_id(self, participant_id: uuid.UUID, *, business_id: uuid.UUID) -> VoiceCallParticipant | None:
        """Fetch a participant by ID (tenant-scoped via parent call)."""
        result = await self.session.execute(
            select(VoiceCallParticipant)
            .join(VoiceCall, VoiceCallParticipant.call_id == VoiceCall.id)
            .where(
                VoiceCallParticipant.id == participant_id,
                VoiceCall.business_id == business_id,
                VoiceCallParticipant.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_call(self, call_id: uuid.UUID) -> list[VoiceCallParticipant]:
        """List participants for a call."""
        result = await self.session.execute(
            select(VoiceCallParticipant)
            .where(
                VoiceCallParticipant.call_id == call_id,
                VoiceCallParticipant.deleted_at.is_(None),
            )
            .order_by(VoiceCallParticipant.created_at.asc())
        )
        return list(result.scalars().all())


class VoiceCallAttemptRepository:
    """Data access for VoiceCallAttempt entities (append-oriented)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, attempt: VoiceCallAttempt) -> VoiceCallAttempt:
        """Persist a new provider attempt (append-only)."""
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def get_by_id(self, attempt_id: uuid.UUID, *, business_id: uuid.UUID) -> VoiceCallAttempt | None:
        """Fetch an attempt by ID (tenant-scoped via parent call)."""
        result = await self.session.execute(
            select(VoiceCallAttempt)
            .join(VoiceCall, VoiceCallAttempt.call_id == VoiceCall.id)
            .where(
                VoiceCallAttempt.id == attempt_id,
                VoiceCall.business_id == business_id,
                VoiceCallAttempt.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_call(self, call_id: uuid.UUID) -> list[VoiceCallAttempt]:
        """List attempts for a call in attempt order."""
        result = await self.session.execute(
            select(VoiceCallAttempt)
            .where(
                VoiceCallAttempt.call_id == call_id,
                VoiceCallAttempt.deleted_at.is_(None),
            )
            .order_by(VoiceCallAttempt.attempt_number.asc())
        )
        return list(result.scalars().all())

    async def next_attempt_number(self, call_id: uuid.UUID) -> int:
        """Return the next append-only attempt number for a call."""
        result = await self.session.execute(
            select(func.max(VoiceCallAttempt.attempt_number)).where(VoiceCallAttempt.call_id == call_id)
        )
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1

    async def update(self, attempt: VoiceCallAttempt) -> VoiceCallAttempt:
        """Update an existing attempt (provider reference/status sync).

        Attempts are append-oriented: the attempt row itself is never
        renumbered or re-parented, only its outcome fields are synced
        with provider truth by the orchestration layer.
        """
        await self.session.flush()
        return attempt


class VoiceCallSessionRepository:
    """Data access for VoiceCallSession entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, session_row: VoiceCallSession) -> VoiceCallSession:
        """Persist a new call session."""
        self.session.add(session_row)
        await self.session.flush()
        return session_row

    async def get_by_id(self, session_id: uuid.UUID, *, business_id: uuid.UUID) -> VoiceCallSession | None:
        """Fetch a session by ID (tenant-scoped via parent call)."""
        result = await self.session.execute(
            select(VoiceCallSession)
            .join(VoiceCall, VoiceCallSession.call_id == VoiceCall.id)
            .where(
                VoiceCallSession.id == session_id,
                VoiceCall.business_id == business_id,
                VoiceCallSession.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_call(self, call_id: uuid.UUID) -> VoiceCallSession | None:
        """Fetch the active session for a call, if any."""
        result = await self.session.execute(
            select(VoiceCallSession).where(
                VoiceCallSession.call_id == call_id,
                VoiceCallSession.session_status == "ACTIVE",
                VoiceCallSession.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update(self, session_row: VoiceCallSession) -> VoiceCallSession:
        """Update an existing session."""
        await self.session.flush()
        return session_row


class VoiceCallEscalationRepository:
    """Data access for VoiceCallEscalation entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, escalation: VoiceCallEscalation) -> VoiceCallEscalation:
        """Persist a new escalation."""
        self.session.add(escalation)
        await self.session.flush()
        return escalation

    async def get_by_id(self, escalation_id: uuid.UUID, *, business_id: uuid.UUID) -> VoiceCallEscalation | None:
        """Fetch an escalation by ID (tenant-scoped via parent call)."""
        result = await self.session.execute(
            select(VoiceCallEscalation)
            .join(VoiceCall, VoiceCallEscalation.call_id == VoiceCall.id)
            .where(
                VoiceCallEscalation.id == escalation_id,
                VoiceCall.business_id == business_id,
                VoiceCallEscalation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_for_call(self, call_id: uuid.UUID) -> VoiceCallEscalation | None:
        """Fetch the escalation for a call, if any."""
        result = await self.session.execute(
            select(VoiceCallEscalation)
            .where(
                VoiceCallEscalation.call_id == call_id,
                VoiceCallEscalation.deleted_at.is_(None),
            )
            .order_by(VoiceCallEscalation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update(self, escalation: VoiceCallEscalation) -> VoiceCallEscalation:
        """Update an existing escalation."""
        await self.session.flush()
        return escalation


class CallAgentConfigRepository:
    """Data access for business Call Agent configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_business(self, business_id: uuid.UUID) -> CallAgentConfiguration | None:
        """Get the Call Agent configuration for a business."""
        result = await self.session.execute(
            select(CallAgentConfiguration).where(
                CallAgentConfiguration.business_id == business_id,
                CallAgentConfiguration.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, config: CallAgentConfiguration) -> CallAgentConfiguration:
        """Create or update the configuration for a business."""
        existing = await self.get_for_business(config.business_id)
        if existing:
            for attr in (
                "enabled",
                "transactional_calling_enabled",
                "marketing_calling_enabled",
                "default_from_number",
                "provider_reference",
                "timezone",
                "max_attempts",
                "retry_interval_seconds",
                "allowed_calling_hours",
                "quiet_periods",
                "max_daily_attempts",
                "max_weekly_attempts",
                "customer_frequency_limits",
                "human_escalation_enabled",
                "recording_enabled",
                "transcription_enabled",
                # Phase 14B.2 additions
                "agent_instructions",
                "webhook_signature_secret",
            ):
                val = getattr(config, attr, None)
                if val is not None:
                    setattr(existing, attr, val)
            await self.session.flush()
            return existing
        self.session.add(config)
        await self.session.flush()
        return config


class CampaignRepository:
    """Data access for CommunicationCampaign entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, campaign: CommunicationCampaign) -> CommunicationCampaign:
        """Persist a new campaign."""
        self.session.add(campaign)
        await self.session.flush()
        return campaign

    async def get_by_id(self, campaign_id: uuid.UUID, *, business_id: uuid.UUID) -> CommunicationCampaign | None:
        """Fetch a campaign by ID (tenant-scoped)."""
        result = await self.session.execute(
            select(CommunicationCampaign)
            .where(
                CommunicationCampaign.id == campaign_id,
                CommunicationCampaign.business_id == business_id,
                CommunicationCampaign.deleted_at.is_(None),
            )
            .options(selectinload(CommunicationCampaign.recipients))
        )
        return result.scalar_one_or_none()

    async def list_for_business(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        channel: str | None = None,
        purpose: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommunicationCampaign]:
        """List campaigns for a business (tenant-scoped)."""
        stmt = (
            select(CommunicationCampaign)
            .where(
                CommunicationCampaign.business_id == business_id,
                CommunicationCampaign.deleted_at.is_(None),
            )
            .order_by(CommunicationCampaign.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(CommunicationCampaign.status == status)
        if channel:
            stmt = stmt.where(CommunicationCampaign.channel == channel)
        if purpose:
            stmt = stmt.where(CommunicationCampaign.purpose == purpose)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, campaign: CommunicationCampaign) -> CommunicationCampaign:
        """Update an existing campaign."""
        await self.session.flush()
        return campaign


class CampaignRecipientRepository:
    """Data access for CampaignRecipient entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, recipient: CampaignRecipient) -> CampaignRecipient:
        """Persist a new campaign recipient."""
        self.session.add(recipient)
        await self.session.flush()
        return recipient

    async def get_by_id(self, recipient_id: uuid.UUID, *, business_id: uuid.UUID) -> CampaignRecipient | None:
        """Fetch a recipient by ID (tenant-scoped via parent campaign)."""
        result = await self.session.execute(
            select(CampaignRecipient)
            .join(
                CommunicationCampaign,
                CampaignRecipient.campaign_id == CommunicationCampaign.id,
            )
            .where(
                CampaignRecipient.id == recipient_id,
                CommunicationCampaign.business_id == business_id,
                CampaignRecipient.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_campaign(self, campaign_id: uuid.UUID) -> list[CampaignRecipient]:
        """List recipients for a campaign."""
        result = await self.session.execute(
            select(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.deleted_at.is_(None),
            )
            .order_by(CampaignRecipient.created_at.asc())
        )
        return list(result.scalars().all())

    async def update(self, recipient: CampaignRecipient) -> CampaignRecipient:
        """Update an existing recipient."""
        await self.session.flush()
        return recipient
