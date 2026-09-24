"""Phase 14B.2 Block D — deterministic campaign execution.

Drives communication campaigns through the existing deterministic
services:  the closed-world communication policy engine (consent /
suppression / DNC / frequency / timing / Brain rules), the voice call
lifecycle, and the voice provider orchestration layer.

Execution is invocation-driven — an API endpoint or worker calls
``process_campaign``.  There is no internal scheduler:  SCHEDULED
campaigns are processed only after an explicit transition to ACTIVE,
and ``activate`` refuses activation before a configured ``start_at``.

Marketing-versus-transactional separation is enforced at three
levels:  the campaign purpose class, the closed-world policy chain
(evaluated with the purpose TYPE), and the governed Brain version
required before a marketing campaign may activate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.voice.base import VoiceProvider
from app.domain.common.enums import (
    CALL_PURPOSE_TYPE,
    AuditEventType,
    CallPurpose,
    CallStatus,
    CallType,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.domain.communication.models import CommunicationAuditEvent
from app.domain.communication.policy import (
    CommunicationPolicyService,
    RecipientContext,
)
from app.domain.communication.repository import AuditRepository
from app.domain.voice.campaign_service import CampaignService
from app.domain.voice.models import (
    CallAgentConfiguration,
    CampaignRecipient,
    CommunicationCampaign,
)
from app.domain.voice.outbox_integration import emit_voice_event
from app.domain.voice.provider_service import VoiceProviderOrchestrationService
from app.domain.voice.repository import (
    CallAgentConfigRepository,
    CampaignRecipientRepository,
    CampaignRepository,
)
from app.domain.voice.service import VoiceCallLifecycleService
from app.exceptions import DomainError, StateTransitionError

logger = logging.getLogger(__name__)

_AUDIT_CHANNEL = "VOICE"

# Call statuses that mean no completed conversation is possible —
# the linked campaign recipient is settled as FAILED.
_FAILURE_CALL_STATUSES = frozenset(
    {
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.DECLINED,
        CallStatus.CANCELLED,
        CallStatus.EXPIRED,
    }
)

# Recipient statuses that still expect campaign settlement.
_OPEN_RECIPIENT_STATUSES = frozenset(
    {
        CampaignRecipientStatus.PENDING,
        CampaignRecipientStatus.ELIGIBLE,
        CampaignRecipientStatus.CONTACTED,
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC (DB round-trips may drop tzinfo)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class CampaignExecutionService:
    """Invocation-driven campaign execution (deterministic only)."""

    def __init__(
        self,
        session: AsyncSession,
        voice_provider: VoiceProvider,
        lifecycle: VoiceCallLifecycleService | None = None,
        policy_service: CommunicationPolicyService | None = None,
    ) -> None:
        self.session = session
        self.voice_provider = voice_provider
        self.lifecycle = lifecycle or VoiceCallLifecycleService(session)
        self.orchestration = VoiceProviderOrchestrationService(session, voice_provider, lifecycle=self.lifecycle)
        self.campaigns = CampaignService(session)
        self.policy = policy_service or CommunicationPolicyService(session)
        self.campaign_repo = CampaignRepository(session)
        self.recipient_repo = CampaignRecipientRepository(session)
        self.config_repo = CallAgentConfigRepository(session)
        self.audit_repo = AuditRepository(session)

    # ── Activation ──

    async def activate(
        self,
        campaign: CommunicationCampaign,
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> CommunicationCampaign:
        """Activate a DRAFT/SCHEDULED campaign under governed rules.

        Marketing-class campaigns carry promoted content and must be
        governed:  they may not activate without a Brain version.
        ``start_at`` is a hard scheduling gate, not a hint.
        """
        purpose_class = CALL_PURPOSE_TYPE[CallPurpose(campaign.purpose)]
        if purpose_class == CallType.MARKETING and campaign.brain_version_id is None:
            raise DomainError("Marketing campaigns require a governing Brain version")

        moment = _aware(now or _utcnow())
        if campaign.start_at is not None and moment < _aware(campaign.start_at):
            raise DomainError("Campaign start_at has not been reached")

        return await self.campaigns.transition_campaign(campaign, CampaignStatus.ACTIVE)

    # ── Deterministic gating ──

    def _in_calling_window(self, config: CallAgentConfiguration, now: datetime) -> tuple[bool, str]:
        """Deterministic calling-window evaluation.

        allowed_calling_hours JSONB:
            {"days": [0-6], "start_hour": int, "end_hour": int}
        (legacy ``"start"``/``"end"`` ``"HH:MM"`` strings accepted)
        quiet_periods JSONB: [{"start": "MM-DD", "end": "MM-DD"}]

        Evaluated in the configured timezone (fallback UTC).
        """
        hours = config.allowed_calling_hours
        quiet_periods = config.quiet_periods
        if not hours and not quiet_periods:
            return True, "no calling window configured"

        tz = ZoneInfo("UTC")
        if config.timezone:
            try:
                tz = ZoneInfo(config.timezone)
            except ZoneInfoNotFoundError:
                tz = ZoneInfo("UTC")
        local = now.astimezone(tz)

        if hours:
            days = hours.get("days")
            if days and local.weekday() not in days:
                return False, (f"weekday {local.weekday()} outside allowed calling days")

            start_hour = self._hour_of(hours.get("start_hour"), hours.get("start"))
            end_hour = self._hour_of(hours.get("end_hour"), hours.get("end"))
            if start_hour is not None and local.hour < start_hour:
                return False, f"before allowed calling hours ({start_hour}:00)"
            if end_hour is not None and local.hour >= end_hour:
                return False, f"after allowed calling hours ({end_hour}:00)"

        for period in quiet_periods or []:
            if self._in_quiet_period(period, local):
                return False, "within quiet period"

        return True, "within calling window"

    @staticmethod
    def _hour_of(hour_value: object, text_value: object) -> int | None:
        """Accept ``start_hour`` ints and legacy ``"HH:MM"`` strings."""
        if hour_value is not None:
            return int(hour_value)  # type: ignore[arg-type]
        if text_value:
            return int(str(text_value).split(":")[0])
        return None

    @staticmethod
    def _in_quiet_period(period: dict, local: datetime) -> bool:
        start = period.get("start")
        end = period.get("end")
        if not start or not end:
            return False
        try:
            s_month, s_day = (int(p) for p in str(start).split("-"))
            e_month, e_day = (int(p) for p in str(end).split("-"))
        except ValueError:
            return False
        md = (local.month, local.day)
        s_md, e_md = (s_month, s_day), (e_month, e_day)
        if s_md <= e_md:
            return s_md <= md <= e_md
        # Range wrapping the year boundary (e.g. 12-24 → 01-02).
        return md >= s_md or md <= e_md

    async def _frequency_check(
        self,
        config: CallAgentConfiguration,
        campaign: CommunicationCampaign,
        recipient: CampaignRecipient,
        *,
        now: datetime,
    ) -> tuple[bool, bool, str]:
        """Deterministic frequency gating.

        Returns ``(allowed, exhausted, reason)``.  ``exhausted`` means
        the recipient's attempt budget is spent (settle as FAILED);
        throughput caps (daily/weekly) only skip this pass so the
        recipient can be retried later.
        """
        if recipient.attempt_count >= config.max_attempts:
            return (
                False,
                True,
                (f"max attempts reached ({recipient.attempt_count}/{config.max_attempts})"),
            )

        limits = config.customer_frequency_limits or {}
        per_campaign = limits.get("per_campaign")
        if per_campaign is not None and recipient.attempt_count >= int(per_campaign):
            return False, True, f"per-campaign limit reached ({per_campaign})"

        daily = config.max_daily_attempts
        weekly = config.max_weekly_attempts
        if daily is None:
            daily = limits.get("per_day")
        if weekly is None:
            weekly = limits.get("per_week")

        if daily is not None:
            count = await self._attempts_in_window(campaign, now - timedelta(days=1))
            if count >= int(daily):
                return False, False, f"daily attempt limit reached ({daily})"

        if weekly is not None:
            count = await self._attempts_in_window(campaign, now - timedelta(weeks=1))
            if count >= int(weekly):
                return False, False, f"weekly attempt limit reached ({weekly})"

        return True, False, "within frequency limits"

    async def _attempts_in_window(self, campaign: CommunicationCampaign, since: datetime) -> int:
        """Count campaign recipients attempted since ``since``."""
        result = await self.session.execute(
            select(func.count())
            .select_from(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.last_attempt_at >= _aware(since),
                CampaignRecipient.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one() or 0)

    # ── Execution ──

    async def process_campaign(
        self,
        campaign: CommunicationCampaign,
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> dict:
        """Process every PENDING recipient of an ACTIVE campaign.

        Per recipient, deterministically in order:
        1. Calling window — outside → SKIPPED
        2. Frequency — budget exhausted → FAILED, throughput cap → SKIPPED
        3. Closed-world policy — DENY → SUPPRESSED,
           REQUIRE_APPROVAL/DEFER/ESCALATE → SKIPPED, ALLOW → proceed
        4. Initiation through the provider orchestration layer —
           terminal failure → FAILED, otherwise CONTACTED

        Re-running does not duplicate calls:  only PENDING recipients
        are processed and the per-recipient idempotency key pins each
        attempt to exactly one VoiceCall.
        """
        moment = _aware(now or _utcnow())
        if CampaignStatus(campaign.status) != CampaignStatus.ACTIVE:
            raise StateTransitionError(f"Campaign '{campaign.id}' is not ACTIVE (status: {campaign.status})")
        config = await self.config_repo.get_for_business(campaign.business_id)
        if config is None:
            raise DomainError("Call Agent is not configured for this business")

        purpose_class = CALL_PURPOSE_TYPE[CallPurpose(campaign.purpose)]
        policy_purpose = "MARKETING" if purpose_class == CallType.MARKETING else "TRANSACTIONAL"

        await self._audit_campaign(
            campaign,
            AuditEventType.CAMPAIGN_PROCESSING_STARTED,
            actor_id=actor_id,
            evidence={
                "campaign_id": str(campaign.id),
                "purpose": campaign.purpose,
                "call_type": purpose_class.value,
            },
        )

        results: dict = {
            "campaign_id": str(campaign.id),
            "status": campaign.status,
            "processed": 0,
            "contacted": 0,
            "suppressed": 0,
            "skipped": 0,
            "failed": 0,
            "halted": False,
            "recipients": [],
        }

        recipients = await self.recipient_repo.list_for_campaign(campaign.id)
        for recipient in recipients:
            if CampaignRecipientStatus(recipient.status) != CampaignRecipientStatus.PENDING:
                continue
            results["processed"] += 1

            # Mid-run cancellation check — a column select deliberately
            # bypasses the identity map so a cancelled campaign stops
            # the run without touching remaining recipients.
            row = await self.session.execute(
                select(CommunicationCampaign.status).where(CommunicationCampaign.id == campaign.id)
            )
            if row.scalar_one() != CampaignStatus.ACTIVE.value:
                results["halted"] = True
                logger.info(
                    "voice_campaign_processing_halted",
                    campaign_id=str(campaign.id),
                )
                break

            # 1. Calling window
            in_window, window_reason = self._in_calling_window(config, moment)
            if not in_window:
                await self._skip_recipient(campaign, recipient, reason=window_reason, actor_id=actor_id)
                results["skipped"] += 1
                results["recipients"].append(
                    {
                        "recipient_id": str(recipient.id),
                        "status": CampaignRecipientStatus.SKIPPED.value,
                        "reason": window_reason,
                    }
                )
                continue

            # 2. Frequency limits
            allowed, exhausted, freq_reason = await self._frequency_check(config, campaign, recipient, now=moment)
            if not allowed:
                target = CampaignRecipientStatus.FAILED if exhausted else CampaignRecipientStatus.SKIPPED
                await self.campaigns.transition_recipient(recipient, target)
                if target == CampaignRecipientStatus.SKIPPED:
                    await self._audit_campaign(
                        campaign,
                        AuditEventType.CAMPAIGN_RECIPIENT_SKIPPED,
                        actor_id=actor_id,
                        recipient=recipient,
                        evidence={"reason": freq_reason},
                    )
                results["failed" if exhausted else "skipped"] += 1
                results["recipients"].append(
                    {
                        "recipient_id": str(recipient.id),
                        "status": target.value,
                        "reason": freq_reason,
                    }
                )
                continue

            # 3. Closed-world policy (channel/purpose/consent/timing/
            #    frequency/Brain — only ALLOW may proceed)
            decision = await self.policy.evaluate(
                business_id=campaign.business_id,
                recipient=RecipientContext(
                    recipient_type="CUSTOMER",
                    customer_id=recipient.customer_id,
                    address=recipient.phone_number,
                    channel="VOICE",
                    purpose=policy_purpose,
                ),
            )
            if decision.decision == "DENY":
                await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.SUPPRESSED)
                await self._audit_campaign(
                    campaign,
                    AuditEventType.CAMPAIGN_RECIPIENT_SUPPRESSED,
                    actor_id=actor_id,
                    recipient=recipient,
                    evidence=decision.to_evidence_dict(),
                )
                results["suppressed"] += 1
                results["recipients"].append(
                    {
                        "recipient_id": str(recipient.id),
                        "status": CampaignRecipientStatus.SUPPRESSED.value,
                        "reason": decision.reason,
                    }
                )
                continue
            if not decision.is_allowed:
                await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.SKIPPED)
                await self._audit_campaign(
                    campaign,
                    AuditEventType.CAMPAIGN_RECIPIENT_SKIPPED,
                    actor_id=actor_id,
                    recipient=recipient,
                    evidence=decision.to_evidence_dict(),
                )
                results["skipped"] += 1
                results["recipients"].append(
                    {
                        "recipient_id": str(recipient.id),
                        "status": CampaignRecipientStatus.SKIPPED.value,
                        "reason": decision.reason,
                    }
                )
                continue

            # 4. Initiation — PENDING → ELIGIBLE → CONTACTED (CONTACTED
            #    records attempt_count / last_attempt_at).
            await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.ELIGIBLE)
            idempotency_key = f"campaign:{campaign.id}:{recipient.id}:{recipient.attempt_count + 1}"
            call = await self.lifecycle.request_call(
                business_id=campaign.business_id,
                to_number=recipient.phone_number,
                purpose=campaign.purpose,
                provider=self.voice_provider.provider_name,
                idempotency_key=idempotency_key,
                customer_id=recipient.customer_id,
                campaign_id=campaign.id,
                brain_version_id=campaign.brain_version_id,
                actor_id=actor_id,
                source="campaign",
            )
            if CallStatus(call.status) == CallStatus.REQUESTED:
                call = await self.lifecycle.authorize_call(call, actor_id=actor_id)
            call = await self.orchestration.initiate_call(call)

            if CallStatus(call.status) in _FAILURE_CALL_STATUSES:
                await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.FAILED)
                results["failed"] += 1
            else:
                await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.CONTACTED)
                results["contacted"] += 1

            results["recipients"].append(
                {
                    "recipient_id": str(recipient.id),
                    "status": recipient.status,
                    "call_id": str(call.id),
                    "call_status": call.status,
                }
            )
            logger.info(
                "campaign_recipient_processed",
                campaign_id=str(campaign.id),
                recipient_id=str(recipient.id),
                call_id=str(call.id),
                call_status=call.status,
            )

        return results

    # ── Outcome settlement ──

    async def complete_campaign_recipient(
        self,
        call: object,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> CampaignRecipient | None:
        """Settle the campaign recipient tied to a terminal call.

        Called when a campaign call reaches a terminal status
        (provider sync / webhook-driven).  ESCALATED calls keep the
        recipient CONTACTED — a human now owns the outcome.  When the
        last open recipient settles, the campaign auto-completes.
        """
        parts = (getattr(call, "idempotency_key", None) or "").split(":")
        if len(parts) != 4 or parts[0] != "campaign":
            return None
        try:
            campaign_id = uuid.UUID(parts[1])
            recipient_id = uuid.UUID(parts[2])
        except ValueError:
            return None

        recipient = await self.recipient_repo.get_by_id(recipient_id, business_id=call.business_id)
        if recipient is None:
            return None
        if CampaignRecipientStatus(recipient.status) != CampaignRecipientStatus.CONTACTED:
            return recipient

        status = CallStatus(call.status)
        if status == CallStatus.COMPLETED:
            await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.COMPLETED)
        elif status in _FAILURE_CALL_STATUSES:
            await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.FAILED)
        else:
            # Non-terminal / escalated — nothing to settle yet.
            return recipient

        logger.info(
            "campaign_recipient_settled",
            campaign_id=str(campaign_id),
            recipient_id=str(recipient.id),
            call_id=str(call.id),
            call_status=status.value,
            recipient_status=recipient.status,
        )
        await self._maybe_complete_campaign(campaign_id=campaign_id, business_id=call.business_id)
        return recipient

    async def _maybe_complete_campaign(self, *, campaign_id: uuid.UUID, business_id: uuid.UUID) -> None:
        """Auto-complete an ACTIVE campaign once no open recipients remain."""
        campaign = await self.campaign_repo.get_by_id(campaign_id, business_id=business_id)
        if campaign is None or CampaignStatus(campaign.status) != CampaignStatus.ACTIVE:
            return
        recipients = await self.recipient_repo.list_for_campaign(campaign_id)
        if any(CampaignRecipientStatus(r.status) in _OPEN_RECIPIENT_STATUSES for r in recipients):
            return
        await self.campaigns.transition_campaign(campaign, CampaignStatus.COMPLETED)
        await emit_voice_event(
            self.session,
            business_id=business_id,
            event_type="voice.campaign_completed",
            aggregate_type="communication_campaign",
            aggregate_id=campaign.id,
            payload={
                "campaign_id": str(campaign.id),
                "name": campaign.name,
                "purpose": campaign.purpose,
            },
        )
        logger.info(
            "voice_campaign_completed",
            campaign_id=str(campaign.id),
            business_id=str(business_id),
        )

    # ── Provenance ──

    async def _skip_recipient(
        self,
        campaign: CommunicationCampaign,
        recipient: CampaignRecipient,
        *,
        reason: str,
        actor_id: uuid.UUID | None,
    ) -> None:
        await self.campaigns.transition_recipient(recipient, CampaignRecipientStatus.SKIPPED)
        await self._audit_campaign(
            campaign,
            AuditEventType.CAMPAIGN_RECIPIENT_SKIPPED,
            actor_id=actor_id,
            recipient=recipient,
            evidence={"reason": reason},
        )

    async def _audit_campaign(
        self,
        campaign: CommunicationCampaign,
        event_type: AuditEventType,
        *,
        actor_id: uuid.UUID | None,
        evidence: dict,
        recipient: CampaignRecipient | None = None,
    ) -> None:
        event = CommunicationAuditEvent(
            event_type=event_type.value,
            actor_id=actor_id,
            business_id=campaign.business_id,
            customer_id=recipient.customer_id if recipient else None,
            channel=_AUDIT_CHANNEL,
            purpose=campaign.purpose,
            communication_id=None,
            brain_version_id=campaign.brain_version_id,
            decision_evidence=evidence,
            metadata_=evidence,
        )
        await self.audit_repo.create(event)
