"""Commercial Policy domain service.

Orchestrates policy resolution (precedence), lifecycle management,
and fee calculation.  The service is the single authoritative entry
point for "which FIELDed fee applies to this transaction?"

Precedence (highest → lowest):
    business_specific → promotion → business_plan →
    category_default  → global_default

AI may READ and EXPLAIN the effective policy but must NEVER:
- Create, modify, or activate a policy
- Override the deterministic fee calculation
- Calculate an authoritative fee
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.commercial_policy.fee_calculator import FeeCalculator, FeeResult
from app.domain.commercial_policy.models import CommercialPolicy
from app.domain.commercial_policy.repository import CommercialPolicyRepository
from app.domain.common.enums import (
    COMMERCIAL_POLICY_PRECEDENCE,
    COMMERCIAL_POLICY_TRANSITIONS,
    CommercialPolicyFeeType,
    CommercialPolicyScope,
    CommercialPolicyStatus,
)
from app.exceptions import (
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from app.logging import get_logger

logger = get_logger(__name__)


class CommercialPolicyService:
    """Commercial policy resolution and lifecycle management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CommercialPolicyRepository(session)
        self._calculator = FeeCalculator()

    # ── Policy resolution (precedence) ────────────────────────────

    async def resolve_effective_policy(
        self,
        *,
        business_id: uuid.UUID,
        category_id: uuid.UUID | None = None,
        promotion_code: str | None = None,
        at_time: datetime | None = None,
    ) -> CommercialPolicy | None:
        """Resolve the single highest-precedence active policy.

        Returns None only if no global default exists — which should
        never happen on a properly configured platform.
        """
        candidates = await self.repo.get_effective_policies(
            business_id=business_id,
            category_id=category_id,
            promotion_code=promotion_code,
            at_time=at_time,
        )

        if not candidates:
            # Fallback: explicit global default lookup
            return await self.repo.get_global_default(at_time=at_time)

        # Sort by precedence (highest first), then by created_at desc
        # for tie-breaking within the same scope tier.
        def _sort_key(p: CommercialPolicy) -> tuple[int, datetime]:
            scope = CommercialPolicyScope(p.scope)
            precedence = COMMERCIAL_POLICY_PRECEDENCE.get(scope, 0)
            return (precedence, p.created_at)

        candidates.sort(key=_sort_key, reverse=True)
        return candidates[0]

    # ── Fee calculation ───────────────────────────────────────────

    async def calculate_fee(
        self,
        *,
        business_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        category_id: uuid.UUID | None = None,
        promotion_code: str | None = None,
        at_time: datetime | None = None,
    ) -> FeeResult:
        """Resolve the applicable policy and calculate the fee.

        This is the primary entry point for Quote / Invoice / Payment
        to determine the FIELDed platform fee.

        The result is deterministic and can be stored as fee_evidence.
        """
        if amount < Decimal("0"):
            raise ValidationError("Transaction amount must be non-negative")

        policy = await self.resolve_effective_policy(
            business_id=business_id,
            category_id=category_id,
            promotion_code=promotion_code,
            at_time=at_time,
        )

        if policy is None:
            raise ValidationError(
                "No commercial policy is configured for this transaction. "
                "A global default policy must exist."
            )

        try:
            return self._calculator.calculate(policy, amount=amount, currency=currency)
        except ValueError as exc:
            raise ValidationError(f"Fee calculation failed: {exc}") from exc

    def calculate_fee_from_policy(
        self,
        policy: CommercialPolicy,
        *,
        amount: Decimal,
        currency: str,
    ) -> FeeResult:
        """Calculate fee from an already-resolved policy (no DB lookup).

        Useful when the caller has already resolved the policy and
        wants to compute the fee deterministically.
        """
        return self._calculator.calculate(policy, amount=amount, currency=currency)

    # ── CRUD ──────────────────────────────────────────────────────

    async def create_policy(
        self,
        *,
        name: str,
        scope: str,
        fee_type: str,
        effective_from: datetime,
        description: str | None = None,
        version: int | None = None,
        business_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
        plan_key: str | None = None,
        promotion_code: str | None = None,
        percentage: str = "0.0000",
        fixed_amount: str = "0.00",
        fixed_currency: str = "GBP",
        effective_until: datetime | None = None,
        eligibility: dict | None = None,
        disclosure: str | None = None,
        config: dict | None = None,
    ) -> CommercialPolicy:
        """Create a new commercial policy in DRAFT status."""
        # Validate scope
        try:
            CommercialPolicyScope(scope)
        except ValueError:
            raise ValidationError(f"Invalid scope: {scope}") from None

        # Validate fee_type
        try:
            CommercialPolicyFeeType(fee_type)
        except ValueError:
            raise ValidationError(f"Invalid fee type: {fee_type}") from None

        # Validate percentage
        try:
            pct = Decimal(percentage)
            if pct < Decimal("0") or pct > Decimal("100"):
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValidationError("Percentage must be between 0 and 100") from None

        # Validate fixed_amount
        try:
            fix = Decimal(fixed_amount)
            if fix < Decimal("0"):
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValidationError("Fixed amount must be non-negative") from None

        # Auto-version if not specified
        if version is None:
            version = await self.repo.get_next_version(scope, name)

        # Scope-specific validation
        if scope == "business_specific" and not business_id:
            raise ValidationError("Business-specific policy requires a business_id")
        if scope == "category_default" and not category_id:
            raise ValidationError("Category default policy requires a category_id")
        if scope == "business_plan" and not business_id:
            raise ValidationError("Business plan policy requires a business_id")
        if scope == "promotion" and not promotion_code and not business_id:
            # Promotions should target either a business or have a code
            logger.warning(
                "promotion_policy_no_target",
                name=name,
                msg="Promotion has neither business_id nor promotion_code",
            )

        policy = CommercialPolicy(
            name=name,
            description=description,
            scope=scope,
            version=version,
            business_id=business_id,
            category_id=category_id,
            plan_key=plan_key,
            promotion_code=promotion_code,
            fee_type=fee_type,
            percentage=percentage,
            fixed_amount=fixed_amount,
            fixed_currency=fixed_currency,
            effective_from=effective_from,
            effective_until=effective_until,
            status=CommercialPolicyStatus.DRAFT,
            eligibility=eligibility,
            disclosure=disclosure,
            config=config,
        )

        policy = await self.repo.create(policy)

        logger.info(
            "commercial_policy_created",
            policy_id=str(policy.id),
            name=name,
            scope=scope,
            version=version,
        )

        return policy

    async def update_policy(
        self,
        policy: CommercialPolicy,
        *,
        description: str | None = None,
        percentage: str | None = None,
        fixed_amount: str | None = None,
        fixed_currency: str | None = None,
        effective_until: datetime | None = None,
        eligibility: dict | None = None,
        disclosure: str | None = None,
        config: dict | None = None,
    ) -> CommercialPolicy:
        """Update a DRAFT policy.  Active policies cannot be edited."""
        if CommercialPolicyStatus(policy.status) != CommercialPolicyStatus.DRAFT:
            raise ValidationError(
                "Only draft policies can be edited. "
                "Create a new version to supersede an active policy."
            )

        if description is not None:
            policy.description = description
        if percentage is not None:
            pct = Decimal(percentage)
            if pct < Decimal("0") or pct > Decimal("100"):
                raise ValidationError("Percentage must be between 0 and 100")
            policy.percentage = percentage
        if fixed_amount is not None:
            fix = Decimal(fixed_amount)
            if fix < Decimal("0"):
                raise ValidationError("Fixed amount must be non-negative")
            policy.fixed_amount = fixed_amount
        if fixed_currency is not None:
            policy.fixed_currency = fixed_currency
        if effective_until is not None:
            policy.effective_until = effective_until
        if eligibility is not None:
            policy.eligibility = eligibility
        if disclosure is not None:
            policy.disclosure = disclosure
        if config is not None:
            policy.config = config

        return await self.repo.update(policy)

    async def transition_policy(
        self,
        policy: CommercialPolicy,
        target_status: CommercialPolicyStatus,
    ) -> CommercialPolicy:
        """Transition a policy's lifecycle status."""
        current = CommercialPolicyStatus(policy.status)
        allowed = COMMERCIAL_POLICY_TRANSITIONS.get(current, set())

        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition policy from '{current.value}' to "
                f"'{target_status.value}'. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        old_status = policy.status
        policy.status = target_status

        # When activating, deactivate any overlapping same-scope policy
        if target_status == CommercialPolicyStatus.ACTIVE:
            await self._deactivate_overlapping(policy)

        await self.repo.update(policy)

        logger.info(
            "commercial_policy_transition",
            policy_id=str(policy.id),
            from_status=old_status,
            to_status=target_status.value,
        )

        return policy

    async def get_policy(self, policy_id: uuid.UUID) -> CommercialPolicy:
        """Get a policy by ID."""
        policy = await self.repo.get_by_id(policy_id)
        if policy is None:
            raise NotFoundError("Commercial policy not found")
        return policy

    async def list_policies(
        self,
        *,
        scope: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CommercialPolicy]:
        """List policies with optional filters."""
        return await self.repo.list_all(scope=scope, status=status, limit=limit, offset=offset)

    # ── Internal helpers ──────────────────────────────────────────

    async def _deactivate_overlapping(self, policy: CommercialPolicy) -> None:
        """Deactivate overlapping policies in the same scope tier + target.

        When a new policy is activated, any existing active policy
        with the same scope + target (business_id, category_id, etc.)
        that overlaps in time should be superseded.

        If the new policy's effective_from is in the future, it does
        NOT supersede currently-effective policies — they remain in
        effect until the new policy's effective_from is reached.
        """
        now = datetime.now(UTC)

        # A future-dated policy must not supersede currently-effective ones.
        if policy.effective_from > now:
            return

        candidates = await self.repo.get_effective_policies(
            business_id=policy.business_id or uuid.UUID(int=0),
            category_id=policy.category_id,
            at_time=now,
        )

        for candidate in candidates:
            if candidate.id == policy.id:
                continue
            if candidate.scope != policy.scope:
                continue
            # Same scope — check if target matches
            if (
                candidate.business_id == policy.business_id
                and candidate.category_id == policy.category_id
                and CommercialPolicyStatus(candidate.status) == CommercialPolicyStatus.ACTIVE
            ):
                candidate.status = CommercialPolicyStatus.SUPERSEDED
                await self.repo.update(candidate)
                logger.info(
                    "commercial_policy_superseded",
                    superseded_id=str(candidate.id),
                    by_id=str(policy.id),
                )
