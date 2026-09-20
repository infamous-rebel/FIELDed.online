"""Business Brain approval policy.

Defines configurable approval requirements for Brain version lifecycle
transitions (REVIEW → APPROVED, APPROVED → ACTIVE).

The default policy allows owner self-approval.  Future iterations may
store per-business policies in the database.

This module is intentionally simple.  It is NOT an enterprise workflow
engine — it provides explicit representation of approval authority so
that the system never buries approval assumptions as hardcoded rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.common.enums import BusinessMemberRole


# ---------------------------------------------------------------------------
# Approval decision
# ---------------------------------------------------------------------------

class ApprovalDecision(StrEnum):
    """Outcome of an approval check."""
    APPROVED = "approved"
    DENIED = "denied"
    SELF_APPROVAL_NOT_PERMITTED = "self_approval_not_permitted"
    INSUFFICIENT_ROLE = "insufficient_role"
    MULTIPLE_APPROVALS_REQUIRED = "multiple_approvals_required"


# ---------------------------------------------------------------------------
# Approval policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApprovalPolicy:
    """Configurable approval policy for Brain version transitions.

    Attributes:
        self_approval_allowed: Whether the version author can also approve
            their own version.  Default True (owner self-approval).
        minimum_approver_role: The minimum role required to approve.
            Default OWNER.
        required_approvals: Number of independent approvals required.
            Default 1.
        sensitive_rule_types: Rule types that require elevated approval
            (e.g., pricing changes may require owner even if admin can
            approve other types).
        approval_timeout_hours: Hours before a pending approval is
            considered timed out.  None = no timeout.
    """
    self_approval_allowed: bool = True
    minimum_approver_role: BusinessMemberRole = BusinessMemberRole.OWNER
    required_approvals: int = 1
    sensitive_rule_types: frozenset[str] = field(default_factory=frozenset)
    sensitive_approver_role: BusinessMemberRole = BusinessMemberRole.OWNER
    approval_timeout_hours: int | None = None

    def check_approval(
        self,
        *,
        approver_role: BusinessMemberRole,
        is_author: bool,
        rule_types: list[str] | None = None,
        existing_approvals: int = 0,
    ) -> ApprovalDecision:
        """Evaluate whether an approval attempt is valid.

        Args:
            approver_role: The role of the person attempting to approve.
            is_author: Whether the approver is also the version author.
            rule_types: The rule types in the version (for sensitive check).
            existing_approvals: Number of approvals already recorded.

        Returns:
            ApprovalDecision indicating the outcome.
        """
        # 1. Check role level
        role_levels = {
            BusinessMemberRole.OWNER: 3,
            BusinessMemberRole.ADMIN: 2,
            BusinessMemberRole.STAFF: 1,
        }
        approver_level = role_levels.get(approver_role, 0)

        # Determine required role (elevated for sensitive rules)
        required_role = self.minimum_approver_role
        if rule_types and self.sensitive_rule_types:
            if any(rt in self.sensitive_rule_types for rt in rule_types):
                required_role = self.sensitive_approver_role

        required_level = role_levels.get(required_role, 0)
        if approver_level < required_level:
            return ApprovalDecision.INSUFFICIENT_ROLE

        # 2. Check self-approval
        if is_author and not self.self_approval_allowed:
            return ApprovalDecision.SELF_APPROVAL_NOT_PERMITTED

        # 3. Check multiple approvals
        if existing_approvals >= self.required_approvals:
            return ApprovalDecision.APPROVED

        # This approval counts
        if existing_approvals + 1 >= self.required_approvals:
            return ApprovalDecision.APPROVED

        return ApprovalDecision.MULTIPLE_APPROVALS_REQUIRED


# ---------------------------------------------------------------------------
# Default policies
# ---------------------------------------------------------------------------

# Default: owner self-approval (matches the frozen architecture decision)
DEFAULT_APPROVAL_POLICY = ApprovalPolicy(
    self_approval_allowed=True,
    minimum_approver_role=BusinessMemberRole.OWNER,
    required_approvals=1,
)

# Strict: no self-approval, requires independent owner approval
STRICT_APPROVAL_POLICY = ApprovalPolicy(
    self_approval_allowed=False,
    minimum_approver_role=BusinessMemberRole.OWNER,
    required_approvals=1,
)

# Enterprise: multiple approvals, sensitive types require owner
ENTERPRISE_APPROVAL_POLICY = ApprovalPolicy(
    self_approval_allowed=False,
    minimum_approver_role=BusinessMemberRole.ADMIN,
    required_approvals=2,
    sensitive_rule_types=frozenset({
        "base_pricing", "surcharge", "discount",
        "price_floor", "price_cap", "cancellation_policy",
        "refund_policy",
    }),
    sensitive_approver_role=BusinessMemberRole.OWNER,
)


# ---------------------------------------------------------------------------
# Policy resolution
# ---------------------------------------------------------------------------

def resolve_approval_policy(
    business_config: dict[str, Any] | None = None,
) -> ApprovalPolicy:
    """Resolve the approval policy for a business.

    Currently returns the default policy.  When per-business policies
    are implemented, this function will look up the business's
    configured policy from the database.

    Args:
        business_config: Optional business-level configuration that
            may override default policy values.

    Returns:
        The ApprovalPolicy to apply.
    """
    if not business_config:
        return DEFAULT_APPROVAL_POLICY

    # Future: read from business_config or database
    # For now, allow basic overrides from config
    return ApprovalPolicy(
        self_approval_allowed=business_config.get(
            "self_approval_allowed", True
        ),
        minimum_approver_role=BusinessMemberRole(
            business_config.get("minimum_approver_role", "owner")
        ),
        required_approvals=business_config.get("required_approvals", 1),
    )
