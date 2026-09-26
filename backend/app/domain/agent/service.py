"""Agent capability and delegation service.

Provides deterministic authorization checks for agent actions.
Every agent action must pass through this service before execution.

Flow:
    1. Resolve the capability for (business, agent_type, capability_type)
    2. Check authority_mode
    3. If DELEGATED, find an active delegation and validate policy constraints
    4. If APPROVAL, require explicit owner approval (proposal flow)
    5. If ASSIST, allow read/propose but block execution
    6. If DISABLED, deny
    7. Log the execution attempt
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agent.models import AgentCapability, AgentDelegation, AgentExecutionLog
from app.domain.common.enums import (
    AgentAuthorityMode,
    AgentCapabilityType,
    AgentDelegationStatus,
    AgentType,
)
from app.exceptions import DomainError

logger = logging.getLogger(__name__)


class AgentCapabilityService:
    """Deterministic agent capability authorization and audit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Capability resolution ---

    async def get_capability(
        self,
        business_id: uuid.UUID,
        agent_type: AgentType | str,
        capability_type: AgentCapabilityType | str,
    ) -> AgentCapability | None:
        """Get the active capability record for a (business, agent, capability)."""
        result = await self.session.execute(
            select(AgentCapability).where(
                AgentCapability.business_id == business_id,
                AgentCapability.agent_type == str(agent_type),
                AgentCapability.capability_type == str(capability_type),
                AgentCapability.is_active.is_(True),
                AgentCapability.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_capability(
        self,
        business_id: uuid.UUID,
        agent_type: AgentType | str,
        capability_type: AgentCapabilityType | str,
        *,
        default_mode: AgentAuthorityMode = AgentAuthorityMode.DISABLED,
    ) -> AgentCapability:
        """Get or create a capability record with the given default mode."""
        existing = await self.get_capability(business_id, agent_type, capability_type)
        if existing is not None:
            return existing

        capability = AgentCapability(
            business_id=business_id,
            agent_type=str(agent_type),
            capability_type=str(capability_type),
            authority_mode=str(default_mode),
            is_active=True,
        )
        self.session.add(capability)
        await self.session.flush()
        return capability

    async def set_authority_mode(
        self,
        business_id: uuid.UUID,
        agent_type: AgentType | str,
        capability_type: AgentCapabilityType | str,
        mode: AgentAuthorityMode,
        *,
        policy_constraints: dict | None = None,
    ) -> AgentCapability:
        """Set the authority mode for a capability. Owner-only operation."""
        capability = await self.get_or_create_capability(
            business_id,
            agent_type,
            capability_type,
            default_mode=mode,
        )
        capability.authority_mode = str(mode)
        if policy_constraints is not None:
            capability.policy_constraints = policy_constraints
        await self.session.flush()
        return capability

    # --- Delegation management ---

    async def create_delegation(
        self,
        business_id: uuid.UUID,
        agent_type: AgentType | str,
        capability_type: AgentCapabilityType | str,
        granted_by: uuid.UUID,
        *,
        expires_at: datetime | None = None,
        reason: str | None = None,
    ) -> AgentDelegation:
        """Create an explicit owner delegation for a capability.

        The capability must exist and not be DISABLED.
        """
        capability = await self.get_capability(business_id, agent_type, capability_type)
        if capability is None:
            raise NotFoundError("Capability not found")
        if capability.authority_mode == AgentAuthorityMode.DISABLED:
            raise DomainError("Cannot delegate a disabled capability")

        delegation = AgentDelegation(
            capability_id=capability.id,
            business_id=business_id,
            agent_type=str(agent_type),
            capability_type=str(capability_type),
            status=AgentDelegationStatus.ACTIVE,
            granted_by=granted_by,
            granted_at=datetime.now(UTC),
            expires_at=expires_at,
            reason=reason,
        )
        self.session.add(delegation)
        await self.session.flush()
        return delegation

    async def revoke_delegation(
        self,
        delegation_id: uuid.UUID,
        revoked_by: uuid.UUID,
        *,
        reason: str | None = None,
    ) -> AgentDelegation:
        """Revoke an active delegation."""
        result = await self.session.execute(
            select(AgentDelegation).where(
                AgentDelegation.id == delegation_id,
                AgentDelegation.deleted_at.is_(None),
            )
        )
        delegation = result.scalar_one_or_none()
        if delegation is None:
            raise NotFoundError("Delegation not found")
        if delegation.status != AgentDelegationStatus.ACTIVE:
            raise DomainError(f"Cannot revoke delegation in status: {delegation.status}")

        delegation.status = AgentDelegationStatus.REVOKED
        delegation.revoked_at = datetime.now(UTC)
        delegation.revoked_by = revoked_by
        if reason:
            delegation.reason = reason
        await self.session.flush()
        return delegation

    async def get_active_delegation(
        self,
        business_id: uuid.UUID,
        agent_type: AgentType | str,
        capability_type: AgentCapabilityType | str,
    ) -> AgentDelegation | None:
        """Find an active, non-expired delegation for the given parameters."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(AgentDelegation).where(
                AgentDelegation.business_id == business_id,
                AgentDelegation.agent_type == str(agent_type),
                AgentDelegation.capability_type == str(capability_type),
                AgentDelegation.status == AgentDelegationStatus.ACTIVE,
                AgentDelegation.deleted_at.is_(None),
            )
        )
        delegations = list(result.scalars().all())

        # Filter out expired
        for d in delegations:
            if d.expires_at and d.expires_at < now:
                d.status = AgentDelegationStatus.EXPIRED
                continue
            return d

        await self.session.flush()
        return None

    # --- Authorization check ---

    async def check_authorization(
        self,
        business_id: uuid.UUID,
        agent_type: AgentType | str,
        capability_type: AgentCapabilityType | str,
        *,
        action_context: dict[str, Any] | None = None,
    ) -> AgentAuthorizationResult:
        """Check whether an agent is authorized to perform a capability.

        Returns an AgentAuthorizationResult with:
        - authorized: bool
        - authority_mode: the resolved mode
        - delegation: the active delegation (if DELEGATED)
        - reason: why authorization succeeded or failed

        This is the main entry point for agent authorization.
        """
        capability = await self.get_capability(business_id, agent_type, capability_type)

        if capability is None:
            return AgentAuthorizationResult(
                authorized=False,
                authority_mode=AgentAuthorityMode.DISABLED,
                delegation=None,
                reason=f"No capability configured for {agent_type}/{capability_type}",
            )

        mode = AgentAuthorityMode(capability.authority_mode)

        if mode == AgentAuthorityMode.DISABLED:
            return AgentAuthorizationResult(
                authorized=False,
                authority_mode=mode,
                delegation=None,
                reason="Capability is disabled",
            )

        if mode == AgentAuthorityMode.ASSIST:
            return AgentAuthorizationResult(
                authorized=True,
                authority_mode=mode,
                delegation=None,
                reason="Assist mode: may propose/interpret, not execute",
            )

        if mode == AgentAuthorityMode.APPROVAL:
            return AgentAuthorizationResult(
                authorized=True,
                authority_mode=mode,
                delegation=None,
                reason="Approval mode: requires explicit owner approval before execution",
            )

        if mode == AgentAuthorityMode.DELEGATED:
            delegation = await self.get_active_delegation(
                business_id,
                agent_type,
                capability_type,
            )
            if delegation is None:
                return AgentAuthorizationResult(
                    authorized=False,
                    authority_mode=mode,
                    delegation=None,
                    reason="Delegated mode but no active delegation found",
                )

            # Validate policy constraints
            if capability.policy_constraints and action_context:
                valid, reason = _validate_policy_constraints(
                    capability.policy_constraints,
                    action_context,
                )
                if not valid:
                    return AgentAuthorizationResult(
                        authorized=False,
                        authority_mode=mode,
                        delegation=delegation,
                        reason=f"Policy constraint violation: {reason}",
                    )

            return AgentAuthorizationResult(
                authorized=True,
                authority_mode=mode,
                delegation=delegation,
                reason="Delegated with active delegation and valid policy",
            )

        return AgentAuthorizationResult(
            authorized=False,
            authority_mode=mode,
            delegation=None,
            reason=f"Unknown authority mode: {mode}",
        )

    # --- Execution audit ---

    async def log_execution(
        self,
        *,
        business_id: uuid.UUID,
        delegation_id: uuid.UUID | None,
        agent_type: str,
        capability_type: str,
        authority_mode: str,
        action_type: str,
        action_input: dict | None = None,
        action_output: dict | None = None,
        validation_passed: bool = False,
        validation_details: dict | None = None,
        status: str = "success",
        error_message: str | None = None,
        evidence: dict | None = None,
        correlation_id: str | None = None,
        related_enquiry_id: uuid.UUID | None = None,
        related_booking_id: uuid.UUID | None = None,
    ) -> AgentExecutionLog:
        """Log an agent execution for audit trail."""
        log_entry = AgentExecutionLog(
            business_id=business_id,
            delegation_id=delegation_id,
            agent_type=agent_type,
            capability_type=capability_type,
            authority_mode=authority_mode,
            action_type=action_type,
            action_input=action_input,
            action_output=action_output,
            validation_passed=validation_passed,
            validation_details=validation_details,
            status=status,
            error_message=error_message,
            evidence=evidence,
            correlation_id=correlation_id,
            related_enquiry_id=related_enquiry_id,
            related_booking_id=related_booking_id,
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry

    # --- Bulk operations ---

    async def list_capabilities(
        self,
        business_id: uuid.UUID,
        *,
        agent_type: str | None = None,
    ) -> list[AgentCapability]:
        """List all active capabilities for a business."""
        query = select(AgentCapability).where(
            AgentCapability.business_id == business_id,
            AgentCapability.is_active.is_(True),
            AgentCapability.deleted_at.is_(None),
        )
        if agent_type:
            query = query.where(AgentCapability.agent_type == agent_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_delegations(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[AgentDelegation]:
        """List delegations for a business."""
        query = select(AgentDelegation).where(
            AgentDelegation.business_id == business_id,
            AgentDelegation.deleted_at.is_(None),
        )
        if status:
            query = query.where(AgentDelegation.status == status)
        query = query.order_by(AgentDelegation.granted_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Authorization result dataclass
# ---------------------------------------------------------------------------


class AgentAuthorizationResult:
    """Result of an agent authorization check."""

    def __init__(
        self,
        *,
        authorized: bool,
        authority_mode: AgentAuthorityMode | str,
        delegation: AgentDelegation | None,
        reason: str,
    ) -> None:
        self.authorized = authorized
        self.authority_mode = authority_mode
        self.delegation = delegation
        self.reason = reason

    def __bool__(self) -> bool:
        return self.authorized


# ---------------------------------------------------------------------------
# Policy constraint validation
# ---------------------------------------------------------------------------


def _validate_policy_constraints(
    constraints: dict[str, Any],
    context: dict[str, Any],
) -> tuple[bool, str]:
    """Validate action context against policy constraints.

    Returns (is_valid, reason_if_invalid).
    """
    # Amount limit
    if "max_amount" in constraints:
        action_amount = context.get("amount")
        if action_amount is not None:
            from decimal import Decimal

            try:
                if Decimal(str(action_amount)) > Decimal(str(constraints["max_amount"])):
                    return False, f"Amount {action_amount} exceeds max {constraints['max_amount']}"
            except Exception:
                return False, "Invalid amount comparison"

    # Currency check
    if "currency" in constraints:
        action_currency = context.get("currency")
        if action_currency and str(action_currency).upper() != str(constraints["currency"]).upper():
            return False, f"Currency {action_currency} not allowed (expected {constraints['currency']})"

    # Requires enquiry
    if constraints.get("requires_enquiry") and not context.get("enquiry_id"):
        return False, "Action requires an associated enquiry"

    return True, ""


# Import at bottom to avoid circular imports
from app.exceptions import NotFoundError  # noqa: E402
