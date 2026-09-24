"""Communication campaign foundation service.

Provides tenant-scoped campaign creation and deterministic campaign /
campaign-recipient status transitions for the Phase 14B.1 foundation.

Campaign execution — audience selection, scheduling, bulk calls,
automated retries, analytics — is explicitly out of scope for 14B.1
and belongs to later 14B blocks.  Recipients never bypass the
existing consent/suppression/DNC/frequency/timing/Business Brain/
authorization policy chain; eligibility evaluation happens at
execution time.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.enums import (
    CAMPAIGN_RECIPIENT_TRANSITIONS,
    CAMPAIGN_TRANSITIONS,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.domain.voice.models import CampaignRecipient, CommunicationCampaign
from app.domain.voice.repository import (
    CampaignRecipientRepository,
    CampaignRepository,
)
from app.exceptions import NotFoundError, StateTransitionError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CampaignService:
    """Deterministic campaign lifecycle foundation (no execution)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaign_repo = CampaignRepository(session)
        self.recipient_repo = CampaignRecipientRepository(session)

    async def create_campaign(
        self,
        *,
        business_id: uuid.UUID,
        name: str,
        channel: str,
        purpose: str,
        description: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        brain_version_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
    ) -> CommunicationCampaign:
        """Create a tenant-scoped campaign in DRAFT status."""
        campaign = CommunicationCampaign(
            business_id=business_id,
            name=name,
            description=description,
            channel=channel,
            purpose=purpose,
            status=CampaignStatus.DRAFT.value,
            start_at=start_at,
            end_at=end_at,
            brain_version_id=brain_version_id,
            created_by=created_by,
        )
        campaign = await self.campaign_repo.create(campaign)

        logger.info(
            "communication_campaign_created",
            campaign_id=str(campaign.id),
            business_id=str(business_id),
            channel=campaign.channel,
            purpose=campaign.purpose,
        )
        return campaign

    async def transition_campaign(
        self,
        campaign: CommunicationCampaign,
        target_status: CampaignStatus,
    ) -> CommunicationCampaign:
        """Transition a campaign to a new status (validated)."""
        current = CampaignStatus(campaign.status)
        allowed = CAMPAIGN_TRANSITIONS.get(current, set())
        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition campaign from '{current.value}' to "
                f"'{target_status.value}'. Allowed: "
                f"{[s.value for s in allowed] or 'none (terminal state)'}"
            )

        campaign.status = target_status.value
        campaign = await self.campaign_repo.update(campaign)

        logger.info(
            "communication_campaign_transition",
            campaign_id=str(campaign.id),
            from_status=current.value,
            to_status=campaign.status,
        )
        return campaign

    async def get_campaign(self, campaign_id: uuid.UUID, *, business_id: uuid.UUID) -> CommunicationCampaign:
        """Fetch a campaign (tenant-scoped) or raise NotFoundError."""
        campaign = await self.campaign_repo.get_by_id(campaign_id, business_id=business_id)
        if campaign is None:
            raise NotFoundError("Campaign not found")
        return campaign

    # ── Recipients (foundation only — no execution) ──

    async def add_recipient(
        self,
        campaign: CommunicationCampaign,
        *,
        phone_number: str,
        customer_id: uuid.UUID | None = None,
    ) -> CampaignRecipient:
        """Add a recipient to a campaign in PENDING status."""
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            customer_id=customer_id,
            phone_number=phone_number,
            status=CampaignRecipientStatus.PENDING.value,
        )
        return await self.recipient_repo.create(recipient)

    async def transition_recipient(
        self,
        recipient: CampaignRecipient,
        target_status: CampaignRecipientStatus,
    ) -> CampaignRecipient:
        """Transition a campaign recipient (validated)."""
        current = CampaignRecipientStatus(recipient.status)
        allowed = CAMPAIGN_RECIPIENT_TRANSITIONS.get(current, set())
        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition campaign recipient from "
                f"'{current.value}' to '{target_status.value}'. Allowed: "
                f"{[s.value for s in allowed] or 'none (terminal state)'}"
            )

        recipient.status = target_status.value
        if target_status == CampaignRecipientStatus.CONTACTED:
            recipient.attempt_count += 1
            recipient.last_attempt_at = _utcnow()
        elif target_status == CampaignRecipientStatus.COMPLETED:
            recipient.completed_at = _utcnow()

        return await self.recipient_repo.update(recipient)
