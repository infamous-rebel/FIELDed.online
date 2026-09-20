"""Communication Policy Engine.

Deterministic, closed-world governance for all outbound communications.

The policy engine combines:
- Business operational configuration (channels, purposes)
- Recipient eligibility
- Consent / suppression / DNC
- Timing / calling hours
- Frequency limits
- Business Brain communication rules
- Approval requirements
- Authorization

Into a single decision: ALLOW, DENY, REQUIRE_APPROVAL, DEFER, ESCALATE.

Only ALLOW may proceed to provider execution.

Closed-world: missing governance → REQUIRE_APPROVAL, never silent ALLOW.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.business.models import BrainVersion, BusinessBrain, BusinessRule
from app.domain.communication.models import (
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    CustomerCommunicationPreference,
)

logger = logging.getLogger(__name__)


@dataclass
class RecipientContext:
    """Context about the intended recipient.

    Provided by the orchestration layer before policy evaluation.
    """

    recipient_type: str  # CUSTOMER, STAFF, EXTERNAL, OTHER
    user_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    address: str | None = None  # email/phone
    channel: str = ""  # EMAIL, SMS, etc.
    purpose: str = ""  # TRANSACTIONAL, MARKETING, etc.


@dataclass
class PolicyDecision:
    """Result of a policy evaluation.

    Deterministic and auditable.  Every decision preserves
    the evidence that produced it.
    """

    decision: str  # ALLOW, DENY, REQUIRE_APPROVAL, DEFER, ESCALATE
    reason: str
    brain_version_id: uuid.UUID | None = None
    matched_rules: list[dict] = field(default_factory=list)
    consent_state: dict | None = None
    suppression_state: dict | None = None
    frequency_state: dict | None = None
    timing_state: dict | None = None
    recipient_context: RecipientContext | None = None

    @property
    def is_allowed(self) -> bool:
        return self.decision == "ALLOW"

    def to_evidence_dict(self) -> dict:
        """Serialize decision evidence for audit storage."""
        return {
            "decision": self.decision,
            "reason": self.reason,
            "brain_version_id": str(self.brain_version_id) if self.brain_version_id else None,
            "matched_rules": self.matched_rules,
            "consent_state": self.consent_state,
            "suppression_state": self.suppression_state,
            "frequency_state": self.frequency_state,
            "timing_state": self.timing_state,
        }


class CommunicationPolicyService:
    """Evaluates communication policy deterministically.

    Operates closed-world: if required governance data is absent,
    returns REQUIRE_APPROVAL rather than silently allowing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def evaluate(
        self,
        *,
        business_id: uuid.UUID,
        recipient: RecipientContext,
    ) -> PolicyDecision:
        """Evaluate whether a communication is allowed.

        Steps:
        1. Check channel is enabled for the business
        2. Check purpose is enabled for the business
        3. Check recipient consent / suppression / DNC
        4. Check timing restrictions
        5. Check frequency limits
        6. Check Business Brain communication rules
        7. Return final decision with full evidence
        """
        # Step 1: Channel configuration
        channel_config = await self._get_channel_config(business_id, recipient.channel)
        if channel_config is None:
            return PolicyDecision(
                decision="REQUIRE_APPROVAL",
                reason=f"No channel configuration found for '{recipient.channel}'",
                recipient_context=recipient,
            )
        if not channel_config.enabled:
            return PolicyDecision(
                decision="DENY",
                reason=f"Channel '{recipient.channel}' is disabled for this business",
                recipient_context=recipient,
            )

        # Step 2: Purpose configuration
        purpose_config = await self._get_purpose_config(business_id, recipient.purpose)
        if purpose_config is None:
            return PolicyDecision(
                decision="REQUIRE_APPROVAL",
                reason=f"No purpose configuration found for '{recipient.purpose}'",
                recipient_context=recipient,
            )
        if not purpose_config.enabled:
            return PolicyDecision(
                decision="DENY",
                reason=f"Purpose '{recipient.purpose}' is disabled for this business",
                recipient_context=recipient,
            )

        # Check permitted channels
        if purpose_config.permitted_channels:
            permitted = purpose_config.permitted_channels
            if isinstance(permitted, list) and recipient.channel not in permitted:
                return PolicyDecision(
                    decision="DENY",
                    reason=(
                        f"Channel '{recipient.channel}' not permitted for "
                        f"purpose '{recipient.purpose}'"
                    ),
                    recipient_context=recipient,
                )

        # Step 3: Consent / suppression / DNC
        consent_result = await self._check_consent(
            business_id=business_id,
            recipient=recipient,
        )
        if consent_result["decision"] == "DENY":
            return PolicyDecision(
                decision="DENY",
                reason=consent_result["reason"],
                consent_state=consent_result,
                recipient_context=recipient,
            )
        if consent_result["decision"] == "REQUIRE_APPROVAL":
            return PolicyDecision(
                decision="REQUIRE_APPROVAL",
                reason=consent_result["reason"],
                consent_state=consent_result,
                recipient_context=recipient,
            )

        # Step 4: Timing restrictions
        timing_result = await self._check_timing(
            business_id=business_id,
            recipient=recipient,
        )
        if timing_result["decision"] == "DENY":
            return PolicyDecision(
                decision="DENY",
                reason=timing_result["reason"],
                timing_state=timing_result,
                recipient_context=recipient,
            )
        if timing_result["decision"] == "DEFER":
            return PolicyDecision(
                decision="DEFER",
                reason=timing_result["reason"],
                timing_state=timing_result,
                recipient_context=recipient,
            )

        # Step 5: Frequency limits
        frequency_result = await self._check_frequency(
            business_id=business_id,
            recipient=recipient,
        )
        if frequency_result["decision"] == "DENY":
            return PolicyDecision(
                decision="DENY",
                reason=frequency_result["reason"],
                frequency_state=frequency_result,
                recipient_context=recipient,
            )

        # Step 6: Business Brain communication rules
        brain_result = await self._check_brain_rules(
            business_id=business_id,
            recipient=recipient,
        )
        if brain_result["decision"] == "DENY":
            return PolicyDecision(
                decision="DENY",
                reason=brain_result["reason"],
                brain_version_id=brain_result.get("brain_version_id"),
                matched_rules=brain_result.get("matched_rules", []),
                recipient_context=recipient,
            )
        if brain_result["decision"] == "REQUIRE_APPROVAL":
            return PolicyDecision(
                decision="REQUIRE_APPROVAL",
                reason=brain_result["reason"],
                brain_version_id=brain_result.get("brain_version_id"),
                matched_rules=brain_result.get("matched_rules", []),
                recipient_context=recipient,
            )
        if brain_result["decision"] == "ESCALATE":
            return PolicyDecision(
                decision="ESCALATE",
                reason=brain_result["reason"],
                brain_version_id=brain_result.get("brain_version_id"),
                matched_rules=brain_result.get("matched_rules", []),
                recipient_context=recipient,
            )

        # All checks passed
        return PolicyDecision(
            decision="ALLOW",
            reason="All policy checks passed",
            brain_version_id=brain_result.get("brain_version_id"),
            matched_rules=brain_result.get("matched_rules", []),
            consent_state=consent_result,
            suppression_state={"suppressed": False},
            frequency_state=frequency_result,
            timing_state=timing_result,
            recipient_context=recipient,
        )

    async def _get_channel_config(
        self, business_id: uuid.UUID, channel: str
    ) -> BusinessCommunicationChannel | None:
        """Get business channel configuration."""
        result = await self.session.execute(
            select(BusinessCommunicationChannel).where(
                BusinessCommunicationChannel.business_id == business_id,
                BusinessCommunicationChannel.channel == channel,
                BusinessCommunicationChannel.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_purpose_config(
        self, business_id: uuid.UUID, purpose: str
    ) -> BusinessCommunicationPurpose | None:
        """Get business purpose configuration."""
        result = await self.session.execute(
            select(BusinessCommunicationPurpose).where(
                BusinessCommunicationPurpose.business_id == business_id,
                BusinessCommunicationPurpose.purpose == purpose,
                BusinessCommunicationPurpose.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _check_consent(
        self,
        *,
        business_id: uuid.UUID,
        recipient: RecipientContext,
    ) -> dict:
        """Check recipient consent, suppression, and DNC status.

        Closed-world: if customer has no preference record at all,
        return REQUIRE_APPROVAL for non-transactional purposes.
        Transactional communications are allowed without explicit
        consent (they are operationally necessary).
        """
        # STAFF and EXTERNAL recipients bypass consent checks
        if recipient.recipient_type in ("STAFF", "EXTERNAL", "OTHER"):
            return {"decision": "PASS", "reason": "Non-customer recipient"}

        if recipient.customer_id is None:
            return {
                "decision": "REQUIRE_APPROVAL",
                "reason": "No customer_id for consent check",
            }

        # Transactional purpose: always allowed (operationally necessary)
        if recipient.purpose == "TRANSACTIONAL":
            return {
                "decision": "PASS",
                "reason": "Transactional purpose bypasses consent",
            }

        # Look up preferences: most specific first, then broader
        # 1. Exact match (channel + purpose)
        pref = await self._get_preference(
            recipient.customer_id,
            business_id,
            channel=recipient.channel,
            purpose=recipient.purpose,
        )
        # 2. Channel-specific, any purpose
        if pref is None:
            pref = await self._get_preference(
                recipient.customer_id,
                business_id,
                channel=recipient.channel,
                purpose=None,
            )
        # 3. Purpose-specific, any channel
        if pref is None:
            pref = await self._get_preference(
                recipient.customer_id,
                business_id,
                channel=None,
                purpose=recipient.purpose,
            )
        # 4. Global preference (no channel, no purpose)
        if pref is None:
            pref = await self._get_preference(
                recipient.customer_id,
                business_id,
                channel=None,
                purpose=None,
            )

        # No preference record at all
        if pref is None:
            # Closed-world: missing consent → REQUIRE_APPROVAL
            return {
                "decision": "REQUIRE_APPROVAL",
                "reason": "No consent preference found for customer",
            }

        # Check DNC
        if pref.do_not_contact:
            return {
                "decision": "DENY",
                "reason": "Customer has do-not-contact flag",
                "do_not_contact": True,
            }

        # Check suppression
        if pref.suppression:
            return {
                "decision": "DENY",
                "reason": f"Customer is suppressed: {pref.suppression_reason or 'no reason'}",
                "suppressed": True,
                "suppression_reason": pref.suppression_reason,
            }

        # Check opt-in
        if pref.opt_in:
            return {
                "decision": "PASS",
                "reason": "Customer has opted in",
                "opt_in": True,
                "consent_state": pref.consent_state,
            }

        # No explicit opt-in → REQUIRE_APPROVAL
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "No explicit opt-in consent found",
            "consent_state": pref.consent_state,
        }

    async def _get_preference(
        self,
        customer_id: uuid.UUID,
        business_id: uuid.UUID,
        *,
        channel: str | None,
        purpose: str | None,
    ) -> CustomerCommunicationPreference | None:
        """Get a specific preference record."""
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

    async def _check_timing(
        self,
        *,
        business_id: uuid.UUID,
        recipient: RecipientContext,
    ) -> dict:
        """Check timing restrictions (calling hours, quiet periods).

        Reads timing rules from Brain communication_config.
        If no timing rules are configured, allows by default.
        """
        brain_version = await self._get_active_brain_version(business_id)
        if brain_version is None:
            return {"decision": "PASS", "reason": "No brain version for timing check"}

        comm_config = brain_version.communication_config or {}
        timing_rules = comm_config.get("timing_rules", {})

        if not timing_rules:
            return {"decision": "PASS", "reason": "No timing restrictions configured"}

        # Check quiet hours
        quiet_hours = timing_rules.get("quiet_hours")
        if quiet_hours:
            now = datetime.now(UTC)
            hour = now.hour
            start = quiet_hours.get("start", 0)
            end = quiet_hours.get("end", 8)
            if start <= end:
                if start <= hour < end:
                    return {
                        "decision": "DEFER",
                        "reason": f"Communication deferred: quiet hours {start}:00-{end}:00",
                    }
            else:  # overnight range (e.g., 22:00 - 07:00)
                if hour >= start or hour < end:
                    return {
                        "decision": "DEFER",
                        "reason": f"Communication deferred: quiet hours {start}:00-{end}:00",
                    }

        return {"decision": "PASS", "reason": "Timing check passed"}

    async def _check_frequency(
        self,
        *,
        business_id: uuid.UUID,
        recipient: RecipientContext,
    ) -> dict:
        """Check frequency limits.

        Reads frequency rules from Brain communication_config.
        Counts recent communications to the same recipient.
        """
        brain_version = await self._get_active_brain_version(business_id)
        if brain_version is None:
            return {"decision": "PASS", "reason": "No brain version for frequency check"}

        comm_config = brain_version.communication_config or {}
        frequency_rules = comm_config.get("frequency_rules", {})

        if not frequency_rules:
            return {"decision": "PASS", "reason": "No frequency limits configured"}

        # Check max communications per period
        max_per_day = frequency_rules.get("max_per_day")
        if max_per_day and recipient.customer_id:
            from app.domain.communication.models import Communication

            # Count today's communications to this customer
            now = datetime.now(UTC)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            result = await self.session.execute(
                select(func.count())
                .select_from(Communication)
                .where(
                    Communication.business_id == business_id,
                    Communication.customer_id == recipient.customer_id,
                    Communication.channel == recipient.channel,
                    Communication.created_at >= day_start,
                    Communication.deleted_at.is_(None),
                )
            )
            count = result.scalar_one()

            if count >= max_per_day:
                return {
                    "decision": "DENY",
                    "reason": f"Frequency limit exceeded: {count}/{max_per_day} per day",
                    "count": count,
                    "limit": max_per_day,
                }

        return {"decision": "PASS", "reason": "Frequency check passed"}

    async def _check_brain_rules(
        self,
        *,
        business_id: uuid.UUID,
        recipient: RecipientContext,
    ) -> dict:
        """Check Business Brain communication rules.

        Reads communication-type rules from the active BrainVersion.
        Rules can DENY, ESCALATE, or REQUIRE_APPROVAL.
        """
        brain_version = await self._get_active_brain_version(business_id)
        if brain_version is None:
            # Closed-world: no brain → REQUIRE_APPROVAL
            return {
                "decision": "REQUIRE_APPROVAL",
                "reason": "No active Business Brain version found",
            }

        # Get communication rules
        result = await self.session.execute(
            select(BusinessRule)
            .where(
                BusinessRule.brain_version_id == brain_version.id,
                BusinessRule.rule_type == "communication",
                BusinessRule.is_active.is_(True),
                BusinessRule.deleted_at.is_(None),
            )
            .order_by(BusinessRule.priority.desc())
        )
        rules = list(result.scalars().all())

        matched_rules: list[dict] = []

        for rule in rules:
            rule_data = rule.rule_data or {}

            # Check if rule applies to this channel/purpose
            rule_channels = rule_data.get("channels", [])
            rule_purposes = rule_data.get("purposes", [])

            if rule_channels and recipient.channel not in rule_channels:
                continue
            if rule_purposes and recipient.purpose not in rule_purposes:
                continue

            # Rule matches — check its action
            action = rule_data.get("action", "").upper()
            matched_rules.append(
                {
                    "rule_id": str(rule.id),
                    "name": rule.name,
                    "action": action,
                    "reason": rule_data.get("reason", ""),
                }
            )

            if action == "DENY":
                return {
                    "decision": "DENY",
                    "reason": f"Brain rule '{rule.name}' denies communication",
                    "brain_version_id": brain_version.id,
                    "matched_rules": matched_rules,
                }
            if action == "ESCALATE":
                return {
                    "decision": "ESCALATE",
                    "reason": f"Brain rule '{rule.name}' requires escalation",
                    "brain_version_id": brain_version.id,
                    "matched_rules": matched_rules,
                }
            if action == "REQUIRE_APPROVAL":
                return {
                    "decision": "REQUIRE_APPROVAL",
                    "reason": f"Brain rule '{rule.name}' requires approval",
                    "brain_version_id": brain_version.id,
                    "matched_rules": matched_rules,
                }

        return {
            "decision": "PASS",
            "reason": "Brain rules check passed",
            "brain_version_id": brain_version.id,
            "matched_rules": matched_rules,
        }

    async def _get_active_brain_version(self, business_id: uuid.UUID) -> BrainVersion | None:
        """Get the active BrainVersion for a business."""
        result = await self.session.execute(
            select(BrainVersion)
            .join(BusinessBrain, BusinessBrain.id == BrainVersion.brain_id)
            .where(
                BusinessBrain.business_id == business_id,
                BusinessBrain.active_version_id == BrainVersion.id,
                BrainVersion.status == "active",
                BrainVersion.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
