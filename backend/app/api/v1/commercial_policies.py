"""Commercial Policy API endpoints.

Provides access to the FIELDed commercial policy engine:
- List / create / update / transition policies
- Resolve the effective policy for a business context
- Calculate the fee for a given transaction context

AI may READ and EXPLAIN policies but must NEVER create, modify,
activate, or override them through AI-driven paths.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_business_member
from app.database import get_db_session
from app.domain.commercial_policy.models import CommercialPolicy
from app.domain.commercial_policy.schemas import (
    CommercialPolicyCreate,
    CommercialPolicyListRead,
    CommercialPolicyRead,
    CommercialPolicyTransition,
    CommercialPolicyUpdate,
    EffectivePolicyRead,
    FeeBreakdownRead,
    PolicyResolveRequest,
)
from app.domain.commercial_policy.service import CommercialPolicyService
from app.domain.common.enums import CommercialPolicyStatus
from app.domain.identity.models import User
from app.exceptions import ValidationError

router = APIRouter()


# ── Policy CRUD ───────────────────────────────────────────────────


@router.get(
    "/commercial-policies",
    response_model=list[CommercialPolicyListRead],
)
async def list_commercial_policies(
    scope: str | None = Query(None, description="Filter by scope"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """List all commercial policies (authenticated users)."""
    service = CommercialPolicyService(session)
    return await service.list_policies(scope=scope, status=status, limit=limit, offset=offset)


@router.post(
    "/commercial-policies",
    response_model=CommercialPolicyRead,
    status_code=201,
)
async def create_commercial_policy(
    body: CommercialPolicyCreate,
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """Create a new commercial policy (DRAFT status)."""
    service = CommercialPolicyService(session)
    policy = await service.create_policy(
        name=body.name,
        scope=body.scope,
        fee_type=body.fee_type,
        effective_from=body.effective_from,
        description=body.description,
        version=body.version,
        business_id=body.business_id,
        category_id=body.category_id,
        plan_key=body.plan_key,
        promotion_code=body.promotion_code,
        percentage=body.percentage,
        fixed_amount=body.fixed_amount,
        fixed_currency=body.fixed_currency,
        effective_until=body.effective_until,
        eligibility=body.eligibility,
        disclosure=body.disclosure,
        config=body.config,
    )
    return policy


# ── Policy resolution & fee calculation ───────────────────────────
# IMPORTANT: These routes must be registered BEFORE the {policy_id}
# routes to prevent FastAPI from matching "resolve" or "effective"
# as UUID path parameters.


@router.post(
    "/commercial-policies/resolve",
    response_model=FeeBreakdownRead,
)
async def resolve_fee(
    body: PolicyResolveRequest,
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """Resolve the effective policy and calculate the fee.

    Returns a full fee breakdown including customer amount,
    platform fee, business proceeds, and disclosure text.
    """
    try:
        amount = Decimal(body.amount)
    except (InvalidOperation, ValueError):
        raise ValidationError("Invalid amount format") from None

    service = CommercialPolicyService(session)
    result = await service.calculate_fee(
        business_id=body.business_id,
        amount=amount,
        currency=body.currency,
        category_id=body.category_id,
        promotion_code=body.promotion_code,
    )

    return FeeBreakdownRead(
        customer_amount=str(result.customer_amount),
        platform_fee=str(result.platform_fee),
        fee_type=result.fee_type,
        percentage_applied=str(result.percentage_applied),
        fixed_applied=str(result.fixed_applied),
        business_proceeds=str(result.business_proceeds),
        currency=result.currency,
        policy_id=result.policy_id,
        policy_name=result.policy_name,
        policy_scope=result.policy_scope,
        policy_version=result.policy_version,
        effective_from=result.effective_from,
        effective_until=result.effective_until,
        disclosure=result.disclosure,
    )


@router.get(
    "/commercial-policies/effective",
    response_model=EffectivePolicyRead,
)
async def get_effective_policy(
    business_id: uuid.UUID = Query(description="Business ID"),
    category_id: uuid.UUID | None = Query(None, description="Service category ID"),
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """Get the effective commercial policy for a business context.

    Returns the resolved policy and a concise fee summary
    suitable for frontend display/disclosure.
    """
    service = CommercialPolicyService(session)
    policy = await service.resolve_effective_policy(
        business_id=business_id,
        category_id=category_id,
    )

    if policy is None:
        return EffectivePolicyRead(
            policy=None,
            fee_summary="No commercial policy configured.",
        )

    # Build a concise fee summary for display
    fee_summary = _build_fee_summary(policy)

    return EffectivePolicyRead(
        policy=policy,
        fee_summary=fee_summary,
    )


# ── Policy CRUD (by ID) ──────────────────────────────────────────
# These routes use {policy_id} and must come AFTER literal-path routes.


@router.get(
    "/commercial-policies/{policy_id}",
    response_model=CommercialPolicyRead,
)
async def get_commercial_policy(
    policy_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """Get a commercial policy by ID."""
    service = CommercialPolicyService(session)
    return await service.get_policy(policy_id)


@router.patch(
    "/commercial-policies/{policy_id}",
    response_model=CommercialPolicyRead,
)
async def update_commercial_policy(
    policy_id: uuid.UUID,
    body: CommercialPolicyUpdate,
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """Update a DRAFT commercial policy."""
    service = CommercialPolicyService(session)
    policy = await service.get_policy(policy_id)
    return await service.update_policy(
        policy,
        description=body.description,
        percentage=body.percentage,
        fixed_amount=body.fixed_amount,
        fixed_currency=body.fixed_currency,
        effective_until=body.effective_until,
        eligibility=body.eligibility,
        disclosure=body.disclosure,
        config=body.config,
    )


@router.post(
    "/commercial-policies/{policy_id}/transition",
    response_model=CommercialPolicyRead,
)
async def transition_commercial_policy(
    policy_id: uuid.UUID,
    body: CommercialPolicyTransition,
    session: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
):
    """Transition a commercial policy's lifecycle status."""
    service = CommercialPolicyService(session)
    policy = await service.get_policy(policy_id)
    target = CommercialPolicyStatus(body.target_status)
    return await service.transition_policy(policy, target)


@router.get(
    "/businesses/{business_id}/commercial-policy",
    response_model=EffectivePolicyRead,
)
async def get_business_effective_policy(
    business_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _member: User = Depends(require_business_member),
):
    """Get the effective commercial policy for a business (business member).

    Returns the resolved policy and a concise fee summary
    suitable for business-facing display/disclosure.
    """
    service = CommercialPolicyService(session)
    policy = await service.resolve_effective_policy(
        business_id=business_id,
    )

    if policy is None:
        return EffectivePolicyRead(
            policy=None,
            fee_summary="No commercial policy configured.",
        )

    fee_summary = _build_fee_summary(policy)

    return EffectivePolicyRead(
        policy=policy,
        fee_summary=fee_summary,
    )


def _build_fee_summary(policy: CommercialPolicy) -> str:
    """Build a concise human-readable fee summary from a policy."""
    fee_type = policy.fee_type
    pct = str(policy.percentage).rstrip("0").rstrip(".")
    fixed = str(policy.fixed_amount)

    summaries = {
        "zero": "FIELDed platform fee: 0% (launch/onboarding period). Stripe processing fees apply separately.",
        "percentage": f"FIELDed platform fee: {pct}% per completed transaction. Stripe processing fees apply separately.",
        "fixed": f"FIELDed platform fee: {policy.fixed_currency} {fixed} per transaction. Stripe processing fees apply separately.",
        "combined": (
            f"FIELDed platform fee: {pct}% + {policy.fixed_currency} {fixed} per transaction. "
            f"Stripe processing fees apply separately."
        ),
    }
    return summaries.get(fee_type, "FIELDed platform fee applies. Stripe processing fees apply separately.")
