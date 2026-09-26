"""Commercial Policy & Fee Engine unit tests.

Covers:
- FeeCalculator: percentage, fixed, combined, zero, edge cases
- Policy precedence: global → category → plan → promotion → business-specific
- Effective dates: time-bounded policies
- Historical preservation: evidence dict is immutable
- Deterministic repeatability: same input → same output
- Tenant isolation: business-specific policies scoped correctly
- Invalid policy rejection: bad fee types, negative amounts, etc.
- State machine: draft → active → inactive → superseded
- API: CRUD + resolve + effective
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.domain.commercial_policy.fee_calculator import FeeCalculator
from app.domain.commercial_policy.models import CommercialPolicy
from app.domain.commercial_policy.service import CommercialPolicyService
from app.domain.common.enums import (
    COMMERCIAL_POLICY_PRECEDENCE,
    CommercialPolicyFeeType,
    CommercialPolicyScope,
    CommercialPolicyStatus,
)
from app.domain.identity.models import Business, BusinessMember, User
from app.domain.services.models import ServiceCategory
from app.exceptions import StateTransitionError, ValidationError

# ── Helpers ───────────────────────────────────────────────────────


def _make_policy(
    *,
    scope: str = "global_default",
    fee_type: str = "percentage",
    percentage: str = "5.0000",
    fixed_amount: str = "0.00",
    name: str = "Test Policy",
    version: int = 1,
    business_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    promotion_code: str | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    status: str = "active",
    disclosure: str | None = None,
) -> CommercialPolicy:
    """Create a CommercialPolicy instance for testing (not persisted)."""
    now = effective_from or datetime(2026, 1, 1, tzinfo=UTC)
    return CommercialPolicy(
        id=uuid.uuid4(),
        name=name,
        scope=scope,
        version=version,
        business_id=business_id,
        category_id=category_id,
        promotion_code=promotion_code,
        fee_type=fee_type,
        percentage=percentage,
        fixed_amount=fixed_amount,
        fixed_currency="GBP",
        effective_from=now,
        effective_until=effective_until,
        status=status,
        disclosure=disclosure or f"Fee: {fee_type}",
    )


# ── FeeCalculator tests ──────────────────────────────────────────


class TestFeeCalculatorPercentage:
    """Percentage-based fee calculation."""

    def test_percentage_5_percent(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="percentage", percentage="5.0000")
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")

        assert result.platform_fee == Decimal("5.00")
        assert result.customer_amount == Decimal("100.00")
        assert result.business_proceeds == Decimal("95.00")
        assert result.fee_type == "percentage"
        assert result.percentage_applied == Decimal("5.0000")
        assert result.currency == "GBP"

    def test_percentage_2_percent(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="percentage", percentage="2.0000")
        result = calc.calculate(policy, amount=Decimal("200.00"), currency="GBP")

        assert result.platform_fee == Decimal("4.00")
        assert result.business_proceeds == Decimal("196.00")

    def test_percentage_rounds_half_up(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="percentage", percentage="3.0000")
        # 3% of 33.33 = 0.9999 → rounds to 1.00
        result = calc.calculate(policy, amount=Decimal("33.33"), currency="GBP")

        assert result.platform_fee == Decimal("1.00")

    def test_percentage_zero_amount(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="percentage", percentage="5.0000")
        result = calc.calculate(policy, amount=Decimal("0.00"), currency="GBP")

        assert result.platform_fee == Decimal("0.00")
        assert result.business_proceeds == Decimal("0.00")


class TestFeeCalculatorFixed:
    """Fixed-fee calculation."""

    def test_fixed_fee(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="fixed", fixed_amount="2.50", percentage="0.0000")
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")

        assert result.platform_fee == Decimal("2.50")
        assert result.business_proceeds == Decimal("97.50")
        assert result.fixed_applied == Decimal("2.50")

    def test_fixed_fee_independent_of_amount(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="fixed", fixed_amount="5.00", percentage="0.0000")

        r1 = calc.calculate(policy, amount=Decimal("10.00"), currency="GBP")
        r2 = calc.calculate(policy, amount=Decimal("1000.00"), currency="GBP")

        assert r1.platform_fee == r2.platform_fee == Decimal("5.00")


class TestFeeCalculatorCombined:
    """Combined percentage + fixed fee."""

    def test_combined_fee(self):
        calc = FeeCalculator()
        policy = _make_policy(
            fee_type="combined",
            percentage="2.0000",
            fixed_amount="1.00",
        )
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")

        # 2% of 100 = 2.00 + 1.00 fixed = 3.00
        assert result.platform_fee == Decimal("3.00")
        assert result.business_proceeds == Decimal("97.00")
        assert result.percentage_applied == Decimal("2.0000")
        assert result.fixed_applied == Decimal("1.00")


class TestFeeCalculatorZero:
    """Zero-fee (launch / onboarding) policy."""

    def test_zero_fee(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="zero", percentage="0.0000", fixed_amount="0.00")
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")

        assert result.platform_fee == Decimal("0.00")
        assert result.business_proceeds == Decimal("100.00")
        assert result.fee_type == "zero"

    def test_zero_fee_large_amount(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="zero", percentage="0.0000")
        result = calc.calculate(policy, amount=Decimal("99999.99"), currency="GBP")

        assert result.platform_fee == Decimal("0.00")
        assert result.business_proceeds == Decimal("99999.99")


class TestFeeCalculatorEdgeCases:
    """Edge cases and validation."""

    def test_negative_amount_rejected(self):
        calc = FeeCalculator()
        policy = _make_policy()
        with pytest.raises(ValueError, match="non-negative"):
            calc.calculate(policy, amount=Decimal("-10.00"), currency="GBP")

    def test_fee_cannot_exceed_amount(self):
        calc = FeeCalculator()
        # Fixed fee of 10 on a transaction of 5
        policy = _make_policy(fee_type="fixed", fixed_amount="10.00", percentage="0.0000")
        result = calc.calculate(policy, amount=Decimal("5.00"), currency="GBP")

        # Fee is capped at the transaction amount
        assert result.platform_fee == Decimal("5.00")
        assert result.business_proceeds == Decimal("0.00")

    def test_invalid_fee_type_rejected(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="bogus")
        with pytest.raises(ValueError, match="Unknown fee type"):
            calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")

    def test_percentage_over_100_rejected(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="percentage", percentage="150.0000")
        with pytest.raises(ValueError, match="0–100"):
            calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")

    def test_negative_fixed_rejected(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="fixed", fixed_amount="-5.00")
        with pytest.raises(ValueError, match="non-negative"):
            calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")


class TestFeeCalculatorDeterminism:
    """Same input must always produce the same output."""

    def test_deterministic_repeatability(self):
        calc = FeeCalculator()
        policy = _make_policy(fee_type="combined", percentage="3.5000", fixed_amount="0.50")

        results = [
            calc.calculate(policy, amount=Decimal("123.45"), currency="GBP")
            for _ in range(100)
        ]

        first = results[0]
        for r in results[1:]:
            assert r.platform_fee == first.platform_fee
            assert r.business_proceeds == first.business_proceeds
            assert r.customer_amount == first.customer_amount


class TestFeeResultEvidence:
    """FeeResult serialization for transaction evidence."""

    def test_to_evidence_dict(self):
        calc = FeeCalculator()
        policy = _make_policy(
            name="Global 5%",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            disclosure="FIELDed platform fee: 5% per transaction.",
        )
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")
        evidence = result.to_evidence_dict()

        assert evidence["customer_amount"] == "100.00"
        assert evidence["platform_fee"] == "5.00"
        assert evidence["business_proceeds"] == "95.00"
        assert evidence["fee_type"] == "percentage"
        assert evidence["policy_name"] == "Global 5%"
        assert evidence["policy_scope"] == "global_default"
        assert evidence["disclosure"] == "FIELDed platform fee: 5% per transaction."
        assert "Stripe processing fees apply separately" in evidence["stripe_note"]

    def test_evidence_preserves_policy_version(self):
        calc = FeeCalculator()
        policy = _make_policy(name="v3", version=3, fee_type="percentage", percentage="2.0000")
        result = calc.calculate(policy, amount=Decimal("50.00"), currency="GBP")
        evidence = result.to_evidence_dict()

        assert evidence["policy_version"] == 3
        assert evidence["policy_name"] == "v3"


# ── Enum tests ────────────────────────────────────────────────────


class TestCommercialPolicyEnums:
    """Enum values and precedence ordering."""

    def test_scope_values(self):
        assert CommercialPolicyScope.GLOBAL_DEFAULT == "global_default"
        assert CommercialPolicyScope.CATEGORY_DEFAULT == "category_default"
        assert CommercialPolicyScope.BUSINESS_PLAN == "business_plan"
        assert CommercialPolicyScope.PROMOTION == "promotion"
        assert CommercialPolicyScope.BUSINESS_SPECIFIC == "business_specific"

    def test_fee_type_values(self):
        assert CommercialPolicyFeeType.PERCENTAGE == "percentage"
        assert CommercialPolicyFeeType.FIXED == "fixed"
        assert CommercialPolicyFeeType.COMBINED == "combined"
        assert CommercialPolicyFeeType.ZERO == "zero"

    def test_status_values(self):
        assert CommercialPolicyStatus.DRAFT == "draft"
        assert CommercialPolicyStatus.ACTIVE == "active"
        assert CommercialPolicyStatus.INACTIVE == "inactive"
        assert CommercialPolicyStatus.SUPERSEDED == "superseded"

    def test_precedence_ordering(self):
        """Business-specific > promotion > business_plan > category > global."""
        prec = COMMERCIAL_POLICY_PRECEDENCE
        assert prec[CommercialPolicyScope.BUSINESS_SPECIFIC] > prec[CommercialPolicyScope.PROMOTION]
        assert prec[CommercialPolicyScope.PROMOTION] > prec[CommercialPolicyScope.BUSINESS_PLAN]
        assert prec[CommercialPolicyScope.BUSINESS_PLAN] > prec[CommercialPolicyScope.CATEGORY_DEFAULT]
        assert prec[CommercialPolicyScope.CATEGORY_DEFAULT] > prec[CommercialPolicyScope.GLOBAL_DEFAULT]


# ── DB-backed service tests ──────────────────────────────────────


async def _create_business(session, user: User, name: str = "Test Biz") -> Business:
    """Create a test business with the user as owner."""
    business = Business(
        name=name,
        slug=f"biz-{uuid.uuid4().hex[:8]}",
        currency="GBP",
    )
    session.add(business)
    await session.flush()

    member = BusinessMember(
        user_id=user.id,
        business_id=business.id,
        role="owner",
    )
    session.add(member)
    await session.flush()
    return business


async def _create_category(session, name: str = "Plumbing") -> ServiceCategory:
    """Create a test service category."""
    cat = ServiceCategory(name=name, slug=f"cat-{uuid.uuid4().hex[:8]}")
    session.add(cat)
    await session.flush()
    return cat


class TestGlobalDefaultPolicy:
    """Global default policy resolution."""

    @pytest.mark.asyncio
    async def test_global_default_is_used_when_nothing_else(self, db_session, test_user):
        """With only a global default, it is always the effective policy."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Create global default
        await service.create_policy(
            name="FIELDed Standard",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        policies = await service.list_policies()
        await service.transition_policy(policies[0], CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(business_id=business.id)
        assert resolved is not None
        assert resolved.scope == "global_default"
        assert resolved.name == "FIELDed Standard"

    @pytest.mark.asyncio
    async def test_global_default_fee_calculation(self, db_session, test_user):
        """Fee calculation through the global default."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        await service.create_policy(
            name="Standard 5%",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        policies = await service.list_policies()
        await service.transition_policy(policies[0], CommercialPolicyStatus.ACTIVE)

        result = await service.calculate_fee(
            business_id=business.id,
            amount=Decimal("200.00"),
            currency="GBP",
        )

        assert result.platform_fee == Decimal("10.00")
        assert result.business_proceeds == Decimal("190.00")


class TestCategoryDefaultPolicy:
    """Category/segment default policy."""

    @pytest.mark.asyncio
    async def test_category_default_overrides_global(self, db_session, test_user):
        """Category default takes precedence over global default."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)
        category = await _create_category(db_session)

        # Global: 5%
        p1 = await service.create_policy(
            name="Global",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Category: 3%
        p2 = await service.create_policy(
            name="Plumbing 3%",
            scope="category_default",
            fee_type="percentage",
            percentage="3.0000",
            category_id=category.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(
            business_id=business.id,
            category_id=category.id,
        )
        assert resolved is not None
        assert resolved.scope == "category_default"
        assert Decimal(str(resolved.percentage)) == Decimal("3.0000")


class TestBusinessPlanPolicy:
    """Business plan policy."""

    @pytest.mark.asyncio
    async def test_business_plan_overrides_category(self, db_session, test_user):
        """Business plan takes precedence over category default."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)
        category = await _create_category(db_session)

        # Category: 3%
        p1 = await service.create_policy(
            name="Cat 3%",
            scope="category_default",
            fee_type="percentage",
            percentage="3.0000",
            category_id=category.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Business plan: 1%
        p2 = await service.create_policy(
            name="Premium Plan",
            scope="business_plan",
            fee_type="percentage",
            percentage="1.0000",
            business_id=business.id,
            plan_key="premium",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(
            business_id=business.id,
            category_id=category.id,
        )
        assert resolved is not None
        assert resolved.scope == "business_plan"
        assert Decimal(str(resolved.percentage)) == Decimal("1.0000")


class TestPromotionPolicy:
    """Promotional policy."""

    @pytest.mark.asyncio
    async def test_promotion_overrides_business_plan(self, db_session, test_user):
        """Active promotion takes precedence over business plan."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Business plan: 5%
        p1 = await service.create_policy(
            name="Standard Plan",
            scope="business_plan",
            fee_type="percentage",
            percentage="5.0000",
            business_id=business.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Promotion: 0% (launch)
        p2 = await service.create_policy(
            name="Launch Promo",
            scope="promotion",
            fee_type="zero",
            percentage="0.0000",
            business_id=business.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_until=datetime(2027, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(business_id=business.id)
        assert resolved is not None
        assert resolved.scope == "promotion"
        assert resolved.fee_type == "zero"


class TestBusinessSpecificPolicy:
    """Negotiated business-specific policy."""

    @pytest.mark.asyncio
    async def test_business_specific_highest_precedence(self, db_session, test_user):
        """Negotiated agreement overrides all other tiers."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Global: 5%
        p1 = await service.create_policy(
            name="Global",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Promotion: 3%
        p2 = await service.create_policy(
            name="Promo",
            scope="promotion",
            fee_type="percentage",
            percentage="3.0000",
            business_id=business.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        # Negotiated: 1.5%
        p3 = await service.create_policy(
            name="Enterprise Agreement",
            scope="business_specific",
            fee_type="percentage",
            percentage="1.5000",
            business_id=business.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p3, CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(business_id=business.id)
        assert resolved is not None
        assert resolved.scope == "business_specific"
        assert Decimal(str(resolved.percentage)) == Decimal("1.5000")

    @pytest.mark.asyncio
    async def test_business_specific_requires_business_id(self, db_session):
        """Cannot create a business_specific policy without a business_id."""
        service = CommercialPolicyService(db_session)
        with pytest.raises(ValidationError, match="business_id"):
            await service.create_policy(
                name="No Biz",
                scope="business_specific",
                fee_type="percentage",
                percentage="2.0000",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            )


class TestEffectiveDates:
    """Time-bounded policy effectiveness."""

    @pytest.mark.asyncio
    async def test_expired_policy_not_used(self, db_session, test_user):
        """A policy past its effective_until is not returned."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Expired policy
        p1 = await service.create_policy(
            name="Old",
            scope="global_default",
            fee_type="percentage",
            percentage="10.0000",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            effective_until=datetime(2021, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Current policy
        p2 = await service.create_policy(
            name="Current",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2025, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(business_id=business.id)
        assert resolved is not None
        assert resolved.name == "Current"

    @pytest.mark.asyncio
    async def test_future_policy_not_active_yet(self, db_session, test_user):
        """A policy with effective_from in the future is not returned."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Current global
        p1 = await service.create_policy(
            name="Current",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2025, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Future policy
        p2 = await service.create_policy(
            name="Future",
            scope="global_default",
            fee_type="percentage",
            percentage="3.0000",
            effective_from=datetime(2030, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        resolved = await service.resolve_effective_policy(business_id=business.id)
        assert resolved is not None
        assert resolved.name == "Current"


class TestHistoricalPreservation:
    """Historical policy/version preservation."""

    @pytest.mark.asyncio
    async def test_evidence_preserves_policy_at_transaction_time(self, db_session, test_user):
        """Fee evidence captures the policy that governed the fee."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Create and activate a 5% policy
        p1 = await service.create_policy(
            name="Standard v1",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            version=1,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p1, CommercialPolicyStatus.ACTIVE)

        # Calculate fee
        result = await service.calculate_fee(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="GBP",
        )

        evidence = result.to_evidence_dict()

        # Evidence captures the exact policy
        assert evidence["policy_id"] == str(p1.id)
        assert evidence["policy_name"] == "Standard v1"
        assert evidence["policy_version"] == 1
        assert evidence["platform_fee"] == "5.00"

        # Now supersede with a new version at 3%
        await service.transition_policy(p1, CommercialPolicyStatus.SUPERSEDED)
        p2 = await service.create_policy(
            name="Standard v2",
            scope="global_default",
            fee_type="percentage",
            percentage="3.0000",
            version=2,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        )
        await service.transition_policy(p2, CommercialPolicyStatus.ACTIVE)

        # The OLD evidence still references v1 at 5%
        assert evidence["policy_version"] == 1
        assert evidence["platform_fee"] == "5.00"

        # A NEW calculation uses v2 at 3%
        result2 = await service.calculate_fee(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="GBP",
        )
        assert result2.platform_fee == Decimal("3.00")
        assert result2.policy_version == 2


class TestTenantIsolation:
    """Business-specific policies are tenant-isolated."""

    @pytest.mark.asyncio
    async def test_business_specific_not_visible_to_other_business(
        self, db_session, test_user, second_user
    ):
        """A negotiated policy for business A does not affect business B."""
        service = CommercialPolicyService(db_session)
        business_a = await _create_business(db_session, test_user, "Biz A")
        business_b = await _create_business(db_session, second_user, "Biz B")

        # Global: 5%
        p_global = await service.create_policy(
            name="Global",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p_global, CommercialPolicyStatus.ACTIVE)

        # Business A gets 1% negotiated rate
        p_a = await service.create_policy(
            name="A's Deal",
            scope="business_specific",
            fee_type="percentage",
            percentage="1.0000",
            business_id=business_a.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p_a, CommercialPolicyStatus.ACTIVE)

        # Business A → 1%
        resolved_a = await service.resolve_effective_policy(business_id=business_a.id)
        assert resolved_a.scope == "business_specific"
        assert Decimal(str(resolved_a.percentage)) == Decimal("1.0000")

        # Business B → global 5%
        resolved_b = await service.resolve_effective_policy(business_id=business_b.id)
        assert resolved_b.scope == "global_default"
        assert Decimal(str(resolved_b.percentage)) == Decimal("5.0000")


class TestInvalidPolicyRejection:
    """Invalid policies are rejected at creation or calculation."""

    @pytest.mark.asyncio
    async def test_invalid_scope_rejected(self, db_session):
        service = CommercialPolicyService(db_session)
        with pytest.raises(ValidationError, match="Invalid scope"):
            await service.create_policy(
                name="Bad",
                scope="invalid_scope",
                fee_type="percentage",
                percentage="5.0000",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_invalid_fee_type_rejected(self, db_session):
        service = CommercialPolicyService(db_session)
        with pytest.raises(ValidationError, match="Invalid fee type"):
            await service.create_policy(
                name="Bad",
                scope="global_default",
                fee_type="bogus",
                percentage="5.0000",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_percentage_over_100_rejected(self, db_session):
        service = CommercialPolicyService(db_session)
        with pytest.raises(ValidationError, match="Percentage"):
            await service.create_policy(
                name="Bad",
                scope="global_default",
                fee_type="percentage",
                percentage="150.0000",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_negative_fixed_amount_rejected(self, db_session):
        service = CommercialPolicyService(db_session)
        with pytest.raises(ValidationError, match="Fixed amount"):
            await service.create_policy(
                name="Bad",
                scope="global_default",
                fee_type="fixed",
                fixed_amount="-5.00",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_negative_transaction_amount_rejected(self, db_session, test_user):
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        p = await service.create_policy(
            name="Global",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)

        with pytest.raises(ValidationError, match="non-negative"):
            await service.calculate_fee(
                business_id=business.id,
                amount=Decimal("-100.00"),
                currency="GBP",
            )

    @pytest.mark.asyncio
    async def test_no_policy_raises(self, db_session, test_user):
        """With no policies at all, fee calculation raises."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        with pytest.raises(ValidationError, match="No commercial policy"):
            await service.calculate_fee(
                business_id=business.id,
                amount=Decimal("100.00"),
                currency="GBP",
            )


class TestPolicyStateMachine:
    """Policy lifecycle transitions."""

    @pytest.mark.asyncio
    async def test_draft_to_active(self, db_session):
        service = CommercialPolicyService(db_session)
        p = await service.create_policy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert p.status == "draft"

        result = await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_active_to_inactive(self, db_session):
        service = CommercialPolicyService(db_session)
        p = await service.create_policy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)

        result = await service.transition_policy(p, CommercialPolicyStatus.INACTIVE)
        assert result.status == "inactive"

    @pytest.mark.asyncio
    async def test_active_to_superseded(self, db_session):
        service = CommercialPolicyService(db_session)
        p = await service.create_policy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)

        result = await service.transition_policy(p, CommercialPolicyStatus.SUPERSEDED)
        assert result.status == "superseded"

    @pytest.mark.asyncio
    async def test_superseded_is_terminal(self, db_session):
        service = CommercialPolicyService(db_session)
        p = await service.create_policy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)
        await service.transition_policy(p, CommercialPolicyStatus.SUPERSEDED)

        with pytest.raises(StateTransitionError):
            await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)

    @pytest.mark.asyncio
    async def test_cannot_edit_active_policy(self, db_session):
        """Active policies cannot be edited — must create new version."""
        service = CommercialPolicyService(db_session)
        p = await service.create_policy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)

        with pytest.raises(ValidationError, match="Only draft"):
            await service.update_policy(p, percentage="3.0000")

    @pytest.mark.asyncio
    async def test_can_edit_draft_policy(self, db_session):
        service = CommercialPolicyService(db_session)
        p = await service.create_policy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )

        updated = await service.update_policy(p, percentage="3.0000")
        assert Decimal(str(updated.percentage)) == Decimal("3.0000")


class TestZeroFeeLaunchPolicy:
    """Launch/onboarding policy produces fee = 0 through the same engine."""

    @pytest.mark.asyncio
    async def test_launch_policy_zero_fee(self, db_session, test_user):
        """A launch promotion produces platform_fee = 0 using the standard engine."""
        service = CommercialPolicyService(db_session)
        business = await _create_business(db_session, test_user)

        # Launch promo: zero fee for 3 months
        p = await service.create_policy(
            name="Launch Promo",
            scope="promotion",
            fee_type="zero",
            percentage="0.0000",
            fixed_amount="0.00",
            business_id=business.id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_until=datetime(2027, 4, 1, tzinfo=UTC),
            disclosure="FIELDed platform fee: 0% during launch period. Stripe processing fees apply separately.",
        )
        await service.transition_policy(p, CommercialPolicyStatus.ACTIVE)

        result = await service.calculate_fee(
            business_id=business.id,
            amount=Decimal("500.00"),
            currency="GBP",
        )

        assert result.platform_fee == Decimal("0.00")
        assert result.business_proceeds == Decimal("500.00")
        assert result.fee_type == "zero"
        assert "launch period" in (result.disclosure or "")

        # Evidence preserves the zero-fee policy
        evidence = result.to_evidence_dict()
        assert evidence["platform_fee"] == "0.00"
        assert evidence["policy_scope"] == "promotion"


# ── API integration tests ────────────────────────────────────────


class TestCommercialPolicyAPI:
    """API endpoint tests."""

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/commercial-policies")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_and_list(self, client: AsyncClient, auth_headers, db_session):
        # Create
        resp = await client.post(
            "/api/v1/commercial-policies",
            headers=auth_headers,
            json={
                "name": "Global Standard",
                "scope": "global_default",
                "fee_type": "percentage",
                "percentage": "5.0000",
                "effective_from": "2026-01-01T00:00:00Z",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Global Standard"
        assert data["status"] == "draft"

        # List
        resp = await client.get(
            "/api/v1/commercial-policies",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_get_by_id(self, client: AsyncClient, auth_headers, db_session):
        # Create
        resp = await client.post(
            "/api/v1/commercial-policies",
            headers=auth_headers,
            json={
                "name": "Test Policy",
                "scope": "global_default",
                "fee_type": "percentage",
                "percentage": "3.0000",
                "effective_from": "2026-01-01T00:00:00Z",
            },
        )
        policy_id = resp.json()["id"]

        # Get
        resp = await client.get(
            f"/api/v1/commercial-policies/{policy_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == policy_id

    @pytest.mark.asyncio
    async def test_transition(self, client: AsyncClient, auth_headers, db_session):
        # Create
        resp = await client.post(
            "/api/v1/commercial-policies",
            headers=auth_headers,
            json={
                "name": "Transition Test",
                "scope": "global_default",
                "fee_type": "percentage",
                "percentage": "5.0000",
                "effective_from": "2026-01-01T00:00:00Z",
            },
        )
        policy_id = resp.json()["id"]

        # Transition to active
        resp = await client.post(
            f"/api/v1/commercial-policies/{policy_id}/transition",
            headers=auth_headers,
            json={"target_status": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_effective_policy_endpoint(
        self, client: AsyncClient, auth_headers, test_user, db_session
    ):
        business = await _create_business(db_session, test_user)

        # Create and activate global default
        await client.post(
            "/api/v1/commercial-policies",
            headers=auth_headers,
            json={
                "name": "Global",
                "scope": "global_default",
                "fee_type": "percentage",
                "percentage": "5.0000",
                "effective_from": "2026-01-01T00:00:00Z",
                "disclosure": "FIELDed platform fee: 5% per completed transaction.",
            },
        )
        policies = (await client.get("/api/v1/commercial-policies", headers=auth_headers)).json()
        pid = policies[0]["id"]
        await client.post(
            f"/api/v1/commercial-policies/{pid}/transition",
            headers=auth_headers,
            json={"target_status": "active"},
        )

        # Get effective
        resp = await client.get(
            "/api/v1/commercial-policies/effective",
            headers=auth_headers,
            params={"business_id": str(business.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["policy"] is not None
        assert "5%" in data["fee_summary"]
        assert "Stripe" in data["fee_summary"]

    @pytest.mark.asyncio
    async def test_business_effective_endpoint(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        business = await _create_business(db_session, test_user)

        # Create and activate
        resp = await client.post(
            "/api/v1/commercial-policies",
            headers=auth_headers,
            json={
                "name": "Global",
                "scope": "global_default",
                "fee_type": "percentage",
                "percentage": "2.0000",
                "effective_from": "2026-01-01T00:00:00Z",
            },
        )
        pid = resp.json()["id"]
        await client.post(
            f"/api/v1/commercial-policies/{pid}/transition",
            headers=auth_headers,
            json={"target_status": "active"},
        )

        # Business member endpoint
        resp = await client.get(
            f"/api/v1/businesses/{business.id}/commercial-policy",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["policy"] is not None
        assert "2%" in data["fee_summary"]
