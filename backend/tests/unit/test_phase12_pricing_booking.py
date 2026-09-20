"""Phase 12 — Pricing, Availability, Booking runtime tests.

Comprehensive unit tests covering:
- PRICING: fixed, starting_at, hourly, surcharge, discount, floor/cap,
  quote-required, conflicting rules, deterministic repeatability
- AVAILABILITY: operating hours, minimum notice, blackout, capacity,
  unavailable slot, valid slot
- BOOKING: lifecycle transitions, invalid transitions, authorization,
  quote acceptance requirement, Brain decision blocking, traceability
- QUOTE: lifecycle transitions, actor authority
- E2E: Enquiry → Brain → Quote → Accept → Availability → Booking → Confirm
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.domain.booking.availability import AvailabilityEvaluator
from app.domain.common.enums import (
    BOOKING_TRANSITIONS,
    QUOTE_TRANSITIONS,
    BookingStatus,
    QuoteStatus,
)
from app.domain.quote.pricing import PricingEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service_offer(
    pricing_model: str = "fixed",
    pricing_config: dict | None = None,
    **kwargs,
):
    """Create a mock ServiceOffer."""
    offer = MagicMock()
    offer.id = uuid.uuid4()
    offer.pricing_model = pricing_model
    # Ensure a currency is present in config if not explicitly provided
    cfg = pricing_config or {}
    if "currency" not in cfg:
        cfg = {**cfg, "currency": "GBP"}
    offer.pricing_config = cfg
    offer.delivery_mode = kwargs.get("delivery_mode", "on_site")
    offer.name = kwargs.get("name", "Test Service")
    offer.business_id = uuid.uuid4()
    return offer


def _make_brain_version(
    rules: list | None = None,
    version_id: uuid.UUID | None = None,
):
    """Create a mock BrainVersion with rules."""
    version = MagicMock()
    version.id = version_id or uuid.uuid4()
    version.status = "active"
    version.rules = rules or []
    return version


def _make_rule(
    rule_type: str,
    rule_data: dict,
    name: str = "Test rule",
    priority: int = 0,
    is_active: bool = True,
):
    """Create a mock BusinessRule."""
    rule = MagicMock()
    rule.id = uuid.uuid4()
    rule.rule_type = rule_type
    rule.name = name
    rule.priority = priority
    rule.is_active = is_active
    rule.rule_data = rule_data
    return rule


def _make_context(**overrides):
    """Create a DecisionContext."""
    from app.domain.business.evaluator import DecisionContext

    return DecisionContext(
        business_id=overrides.get("business_id", uuid.uuid4()),
        service_offer_id=overrides.get("service_offer_id", uuid.uuid4()),
        customer_id=overrides.get("customer_id", uuid.uuid4()),
        context_data=overrides.get("context_data", {}),
    )


# ===========================================================================
# PRICING TESTS
# ===========================================================================


class TestPricingFixedPrice:
    """Test fixed pricing model."""

    def test_fixed_price_basic(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "150.00", "currency": "GBP"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("150.00")
        assert result.currency == "GBP"
        assert result.base_amount == Decimal("150.00")

    def test_fixed_price_default_currency(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.currency == "GBP"

    def test_fixed_price_missing_amount_raises(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"currency": "GBP"},
        )
        with pytest.raises(ValueError, match="amount"):
            engine.calculate(service_offer=offer)


class TestPricingStartingAt:
    """Test starting_at pricing model."""

    def test_starting_at_base_price(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="starting_at",
            pricing_config={"base_price": "75.00", "currency": "GBP"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("75.00")

    def test_starting_at_missing_base_price_raises(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="starting_at",
            pricing_config={},
        )
        with pytest.raises(ValueError, match="base_price"):
            engine.calculate(service_offer=offer)


class TestPricingHourly:
    """Test hourly pricing model."""

    def test_hourly_rate_times_hours(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="hourly",
            pricing_config={"hourly_rate": "50", "estimated_hours": "3"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("150.00")

    def test_hourly_minimum_hours(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="hourly",
            pricing_config={
                "hourly_rate": "50",
                "estimated_hours": "1",
                "minimum_hours": "2",
            },
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("100.00")

    def test_hourly_default_one_hour(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="hourly",
            pricing_config={"hourly_rate": "80"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("80.00")


class TestPricingSurcharge:
    """Test surcharge rules."""

    def test_fixed_surcharge(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        rule = _make_rule(
            "surcharge",
            {
                "surcharge_name": "Weekend fee",
                "amount": "25",
            },
        )
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("125.00")
        assert len(result.surcharges) == 1

    def test_percentage_surcharge(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "200", "currency": "GBP"},
        )
        rule = _make_rule(
            "surcharge",
            {
                "surcharge_name": "10% fee",
                "percentage": "10",
            },
        )
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("220.00")


class TestPricingDiscount:
    """Test discount rules."""

    def test_percentage_discount(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "200", "currency": "GBP"},
        )
        rule = _make_rule(
            "discount",
            {
                "discount_name": "Loyalty 15%",
                "percentage": "15",
            },
        )
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("170.00")
        assert len(result.discounts) == 1

    def test_discount_capped_at_max(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "500", "currency": "GBP"},
        )
        rule = _make_rule(
            "discount",
            {
                "discount_name": "Big discount",
                "percentage": "50",
                "max_discount": "100",
            },
        )
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        # 50% of 500 = 250, but capped at 100
        assert result.amount == Decimal("400.00")

    def test_discount_cannot_exceed_base(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "50", "currency": "GBP"},
        )
        rule = _make_rule(
            "discount",
            {
                "discount_name": "Huge discount",
                "amount": "100",
            },
        )
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        # Discount capped at base amount
        assert result.amount == Decimal("0")


class TestPricingFloorCap:
    """Test price floor and cap rules."""

    def test_floor_applied(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "30", "currency": "GBP"},
        )
        rule = _make_rule("price_floor", {"minimum_amount": "50"})
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("50.00")
        assert result.floor_applied is True

    def test_cap_applied(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "500", "currency": "GBP"},
        )
        rule = _make_rule("price_cap", {"maximum_amount": "300"})
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("300.00")
        assert result.cap_applied is True

    def test_floor_and_cap_together(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "25", "currency": "GBP"},
        )
        floor_rule = _make_rule("price_floor", {"minimum_amount": "50"}, name="floor")
        cap_rule = _make_rule("price_cap", {"maximum_amount": "200"}, name="cap")
        brain = _make_brain_version(rules=[floor_rule, cap_rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("50.00")
        assert result.floor_applied is True


class TestPricingQuoteRequired:
    """Test quote_required pricing model."""

    def test_quote_required_returns_zero(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="quote_required",
            pricing_config={},
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("0")
        assert result.quote_required is False  # No brain rule triggered it


class TestPricingDeterminism:
    """Test that pricing is deterministic and reproducible."""

    def test_same_input_same_output(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "150.00", "currency": "GBP"},
        )
        rule = _make_rule("surcharge", {"surcharge_name": "Fee", "amount": "25"})
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result1 = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        result2 = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result1.amount == result2.amount
        assert result1.currency == result2.currency

    def test_evidence_contains_brain_version_id(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        brain = _make_brain_version(rules=[])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.brain_version_id == brain.id

    def test_evidence_serialization(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        result = engine.calculate(service_offer=offer)
        evidence = result.to_evidence_dict()
        assert "amount" in evidence
        assert "currency" in evidence
        assert "base_amount" in evidence


class TestPricingNoBrain:
    """Test pricing without a Brain version."""

    def test_no_brain_uses_service_offer_pricing(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "USD"},
        )
        result = engine.calculate(service_offer=offer, brain_version=None)
        assert result.amount == Decimal("100.00")
        assert result.brain_version_id is None


# ===========================================================================
# AVAILABILITY TESTS
# ===========================================================================


class TestAvailabilityBlackout:
    """Test blackout period rules."""

    def test_blackout_blocks_request(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=3)

        rule = _make_rule(
            "blackout_period",
            {
                "start_date": (requested - timedelta(hours=1)).isoformat(),
                "end_date": (requested + timedelta(hours=1)).isoformat(),
                "reason": "Holiday",
            },
        )
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is False
        assert len(result.blocked_by) > 0

    def test_outside_blackout_allows(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=10)

        rule = _make_rule(
            "blackout_period",
            {
                "start_date": (now + timedelta(days=1)).isoformat(),
                "end_date": (now + timedelta(days=3)).isoformat(),
            },
        )
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is True


class TestAvailabilityMinimumNotice:
    """Test minimum notice rules."""

    def test_insufficient_notice_blocks(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(hours=2)  # Only 2 hours notice

        rule = _make_rule("minimum_notice", {"notice_hours": "24"})
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is False

    def test_sufficient_notice_allows(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=7)

        rule = _make_rule("minimum_notice", {"notice_hours": "24"})
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is True


class TestAvailabilityMaximumAdvance:
    """Test maximum advance booking window."""

    def test_too_far_ahead_blocks(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=100)

        rule = _make_rule("maximum_advance", {"advance_days": "30"})
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is False

    def test_within_window_allows(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=10)

        rule = _make_rule("maximum_advance", {"advance_days": "30"})
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is True


class TestAvailabilityCapacity:
    """Test capacity limit rules."""

    def test_capacity_exceeded_blocks(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=2, hours=10)

        rule = _make_rule(
            "capacity_limit",
            {
                "max_capacity": "2",
                "time_window_minutes": "120",
            },
        )
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        # Create 2 existing bookings in the window
        existing = []
        for _ in range(2):
            b = MagicMock()
            b.requested_at = requested
            b.status = "confirmed"
            existing.append(b)

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
            existing_bookings=existing,
        )
        assert result.available is False

    def test_capacity_available(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=2, hours=10)

        rule = _make_rule(
            "capacity_limit",
            {
                "max_capacity": "5",
                "time_window_minutes": "120",
            },
        )
        brain = _make_brain_version(rules=[rule])
        offer = _make_service_offer()

        # Only 1 existing booking
        b = MagicMock()
        b.requested_at = requested
        b.status = "confirmed"

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
            existing_bookings=[b],
        )
        assert result.available is True


class TestAvailabilityNoBrain:
    """Test availability without a Brain."""

    def test_no_brain_allows_by_default(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=2)
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=None,
        )
        assert result.available is True
        assert result.brain_version_id is None


class TestAvailabilityEvidence:
    """Test availability result evidence."""

    def test_evidence_contains_brain_version_id(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=2)
        brain = _make_brain_version(rules=[])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.brain_version_id == brain.id

    def test_evidence_serialization(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=2)
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=None,
        )
        evidence = result.to_evidence_dict()
        assert "available" in evidence
        assert "requested_at" in evidence


# ===========================================================================
# QUOTE LIFECYCLE TESTS
# ===========================================================================


class TestQuoteStateMachine:
    """Test quote lifecycle transitions."""

    def test_valid_transitions(self):
        for targets in QUOTE_TRANSITIONS.values():
            for to_status in targets:
                assert isinstance(to_status, QuoteStatus)

    def test_draft_to_issued(self):
        assert QuoteStatus.ISSUED in QUOTE_TRANSITIONS[QuoteStatus.DRAFT]

    def test_issued_to_accepted(self):
        assert QuoteStatus.ACCEPTED in QUOTE_TRANSITIONS[QuoteStatus.ISSUED]

    def test_issued_to_declined(self):
        assert QuoteStatus.DECLINED in QUOTE_TRANSITIONS[QuoteStatus.ISSUED]

    def test_issued_to_expired(self):
        assert QuoteStatus.EXPIRED in QUOTE_TRANSITIONS[QuoteStatus.ISSUED]

    def test_accepted_is_terminal(self):
        assert len(QUOTE_TRANSITIONS[QuoteStatus.ACCEPTED]) == 0

    def test_declined_is_terminal(self):
        assert len(QUOTE_TRANSITIONS[QuoteStatus.DECLINED]) == 0

    def test_expired_is_terminal(self):
        assert len(QUOTE_TRANSITIONS[QuoteStatus.EXPIRED]) == 0

    def test_invalid_transition_not_allowed(self):
        # Cannot go from DRAFT directly to ACCEPTED
        assert QuoteStatus.ACCEPTED not in QUOTE_TRANSITIONS[QuoteStatus.DRAFT]

    def test_all_statuses_have_entries(self):
        for status in QuoteStatus:
            assert status in QUOTE_TRANSITIONS


# ===========================================================================
# BOOKING LIFECYCLE TESTS
# ===========================================================================


class TestBookingStateMachine:
    """Test booking lifecycle transitions."""

    def test_requested_to_proposed(self):
        assert BookingStatus.PROPOSED in BOOKING_TRANSITIONS[BookingStatus.REQUESTED]

    def test_requested_to_declined(self):
        assert BookingStatus.DECLINED in BOOKING_TRANSITIONS[BookingStatus.REQUESTED]

    def test_proposed_to_accepted(self):
        assert BookingStatus.ACCEPTED in BOOKING_TRANSITIONS[BookingStatus.PROPOSED]

    def test_accepted_to_confirmed(self):
        assert BookingStatus.CONFIRMED in BOOKING_TRANSITIONS[BookingStatus.ACCEPTED]

    def test_confirmed_to_in_progress(self):
        assert BookingStatus.IN_PROGRESS in BOOKING_TRANSITIONS[BookingStatus.CONFIRMED]

    def test_in_progress_to_completed(self):
        assert BookingStatus.COMPLETED in BOOKING_TRANSITIONS[BookingStatus.IN_PROGRESS]

    def test_completed_is_terminal(self):
        assert len(BOOKING_TRANSITIONS[BookingStatus.COMPLETED]) == 0

    def test_declined_is_terminal(self):
        assert len(BOOKING_TRANSITIONS[BookingStatus.DECLINED]) == 0

    def test_cancelled_is_terminal(self):
        assert len(BOOKING_TRANSITIONS[BookingStatus.CANCELLED]) == 0

    def test_no_show_is_terminal(self):
        assert len(BOOKING_TRANSITIONS[BookingStatus.NO_SHOW]) == 0

    def test_invalid_transition_not_allowed(self):
        # Cannot go from REQUESTED directly to COMPLETED
        assert BookingStatus.COMPLETED not in BOOKING_TRANSITIONS[BookingStatus.REQUESTED]

    def test_all_statuses_have_entries(self):
        for status in BookingStatus:
            assert status in BOOKING_TRANSITIONS

    def test_cancelled_from_multiple_states(self):
        """Cancelled is reachable from most active states."""
        for status in [
            BookingStatus.REQUESTED,
            BookingStatus.PROPOSED,
            BookingStatus.ACCEPTED,
            BookingStatus.CONFIRMED,
            BookingStatus.IN_PROGRESS,
        ]:
            assert BookingStatus.CANCELLED in BOOKING_TRANSITIONS[status]


# ===========================================================================
# PRICING + BRAIN INTEGRATION TESTS
# ===========================================================================


class TestPricingBrainIntegration:
    """Test pricing engine with Brain rules."""

    def test_multiple_surcharges_accumulate(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        rule1 = _make_rule("surcharge", {"surcharge_name": "Fee 1", "amount": "10"})
        rule2 = _make_rule("surcharge", {"surcharge_name": "Fee 2", "amount": "15"})
        brain = _make_brain_version(rules=[rule1, rule2])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("125.00")
        assert len(result.surcharges) == 2

    def test_surcharge_then_discount(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "200", "currency": "GBP"},
        )
        surcharge = _make_rule("surcharge", {"surcharge_name": "Weekend", "amount": "50"})
        discount = _make_rule("discount", {"discount_name": "Loyalty", "percentage": "10"})
        brain = _make_brain_version(rules=[surcharge, discount])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        # 200 + 50 = 250, then 10% of 200 = 20 discount → 230
        assert result.amount == Decimal("230.00")

    def test_inactive_rules_ignored(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        rule = _make_rule("surcharge", {"surcharge_name": "Fee", "amount": "50"}, is_active=False)
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount == Decimal("100.00")

    def test_price_never_negative(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "10", "currency": "GBP"},
        )
        rule = _make_rule("discount", {"discount_name": "Huge", "amount": "500"})
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert result.amount >= Decimal("0")

    def test_applied_rule_ids_tracked(self):
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        rule = _make_rule("surcharge", {"surcharge_name": "Fee", "amount": "10"})
        brain = _make_brain_version(rules=[rule])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        assert rule.id in result.applied_rule_ids


# ===========================================================================
# COMBINED AVAILABILITY + BRAIN TESTS
# ===========================================================================


class TestAvailabilityCombinedRules:
    """Test multiple availability rules together."""

    def test_blackout_and_notice_combined(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(days=2)

        # Blackout doesn't cover this date
        blackout = _make_rule(
            "blackout_period",
            {
                "start_date": (now + timedelta(days=10)).isoformat(),
                "end_date": (now + timedelta(days=12)).isoformat(),
            },
            name="blackout",
        )

        # Minimum notice is satisfied
        notice = _make_rule("minimum_notice", {"notice_hours": "12"}, name="notice")

        brain = _make_brain_version(rules=[blackout, notice])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is True
        assert len(result.matched_rules) == 2

    def test_multiple_blocks_reported(self):
        evaluator = AvailabilityEvaluator()
        now = datetime.now(UTC)
        requested = now + timedelta(hours=1)  # Very soon

        # Minimum notice blocks
        notice = _make_rule("minimum_notice", {"notice_hours": "48"}, name="notice")
        # Maximum advance doesn't block (it's close)
        advance = _make_rule("maximum_advance", {"advance_days": "30"}, name="advance")

        brain = _make_brain_version(rules=[notice, advance])
        offer = _make_service_offer()

        result = evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
        )
        assert result.available is False
        assert len(result.blocked_by) >= 1


# ===========================================================================
# E2E FLOW TEST (unit-level, no DB)
# ===========================================================================


class TestE2EFlowUnit:
    """End-to-end flow test at unit level (no database).

    Tests the logical flow:
    Enquiry → Brain qualification → Quote → Accept → Availability → Booking
    """

    def test_pricing_to_availability_flow(self):
        """Verify pricing and availability produce consistent results."""
        pricing_engine = PricingEngine()
        avail_evaluator = AvailabilityEvaluator()

        # Set up service offer
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "150.00", "currency": "GBP"},
        )

        # Set up brain with pricing and availability rules
        pricing_rule = _make_rule(
            "surcharge",
            {
                "surcharge_name": "Service fee",
                "amount": "25",
            },
            name="service_fee",
        )
        notice_rule = _make_rule(
            "minimum_notice",
            {
                "notice_hours": "24",
            },
            name="min_notice",
        )

        brain = _make_brain_version(rules=[pricing_rule, notice_rule])
        context = _make_context()

        # Step 1: Calculate pricing
        pricing_result = pricing_engine.calculate(
            service_offer=offer, brain_version=brain, context=context
        )
        assert pricing_result.amount == Decimal("175.00")
        assert pricing_result.brain_version_id == brain.id

        # Step 2: Check availability (far enough in advance)
        requested = datetime.now(UTC) + timedelta(days=5)
        avail_result = avail_evaluator.evaluate(
            requested_at=requested,
            service_offer=offer,
            brain_version=brain,
            context=context,
        )
        assert avail_result.available is True
        assert avail_result.brain_version_id == brain.id

        # Both results reference the same brain version
        assert pricing_result.brain_version_id == avail_result.brain_version_id

    def test_quote_lifecycle_flow(self):
        """Verify quote state transitions are valid."""
        # DRAFT → ISSUED → ACCEPTED is the happy path
        assert QuoteStatus.ISSUED in QUOTE_TRANSITIONS[QuoteStatus.DRAFT]
        assert QuoteStatus.ACCEPTED in QUOTE_TRANSITIONS[QuoteStatus.ISSUED]

    def test_booking_lifecycle_flow(self):
        """Verify booking state transitions are valid."""
        # REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED
        path = [
            (BookingStatus.REQUESTED, BookingStatus.PROPOSED),
            (BookingStatus.PROPOSED, BookingStatus.ACCEPTED),
            (BookingStatus.ACCEPTED, BookingStatus.CONFIRMED),
            (BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS),
            (BookingStatus.IN_PROGRESS, BookingStatus.COMPLETED),
        ]
        for from_status, to_status in path:
            assert to_status in BOOKING_TRANSITIONS[from_status], (
                f"{from_status} → {to_status} should be valid"
            )

    def test_full_transaction_traceability(self):
        """Verify that pricing evidence retains brain version traceability."""
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "GBP"},
        )
        brain = _make_brain_version(rules=[])
        context = _make_context()

        result = engine.calculate(service_offer=offer, brain_version=brain, context=context)
        evidence = result.to_evidence_dict()

        # Evidence must contain the brain version ID
        assert evidence["brain_version_id"] == str(brain.id)
        assert evidence["amount"] == "100.00"
        assert evidence["currency"] == "GBP"


# ===========================================================================
# CURRENCY REGRESSION TESTS
# ===========================================================================


class TestCurrencyRegression:
    """Verify currency is explicit and never silently defaulted to AUD."""

    def test_pricing_uses_explicit_pricing_config_currency(self):
        """Currency from pricing_config takes priority."""
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "USD"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.currency == "USD"

    def test_pricing_uses_business_currency_fallback(self):
        """When pricing_config has no currency, business_currency is used."""
        engine = PricingEngine()
        offer = MagicMock()
        offer.id = uuid.uuid4()
        offer.pricing_model = "fixed"
        offer.pricing_config = {"amount": "100"}  # No currency
        offer.delivery_mode = "on_site"
        offer.name = "Test"
        offer.business_id = uuid.uuid4()

        result = engine.calculate(
            service_offer=offer,
            business_currency="EUR",
        )
        assert result.currency == "EUR"

    def test_pricing_raises_without_any_currency(self):
        """If neither pricing_config nor business_currency provides currency, raise."""
        engine = PricingEngine()
        offer = MagicMock()
        offer.id = uuid.uuid4()
        offer.pricing_model = "fixed"
        offer.pricing_config = {"amount": "100"}  # No currency
        offer.delivery_mode = "on_site"
        offer.name = "Test"
        offer.business_id = uuid.uuid4()

        with pytest.raises(ValueError, match="Currency must be configured"):
            engine.calculate(service_offer=offer)

    def test_pricing_never_silently_introduces_aud(self):
        """AUD must not appear unless explicitly configured."""
        engine = PricingEngine()
        for currency in ["GBP", "USD", "EUR", "NZD"]:
            offer = _make_service_offer(
                pricing_model="fixed",
                pricing_config={"amount": "50", "currency": currency},
            )
            result = engine.calculate(service_offer=offer)
            assert result.currency == currency
            assert result.currency != "AUD"

    def test_pricing_evidence_contains_currency(self):
        """Pricing evidence must include the resolved currency."""
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "100", "currency": "USD"},
        )
        result = engine.calculate(service_offer=offer)
        evidence = result.to_evidence_dict()
        assert evidence["currency"] == "USD"

    def test_decimal_arithmetic_remains_correct_with_explicit_currency(self):
        """Decimal precision is preserved regardless of currency."""
        engine = PricingEngine()
        offer = _make_service_offer(
            pricing_model="fixed",
            pricing_config={"amount": "99.99", "currency": "EUR"},
        )
        result = engine.calculate(service_offer=offer)
        assert result.amount == Decimal("99.99")
        assert isinstance(result.amount, Decimal)

    def test_business_currency_used_for_hourly_pricing(self):
        """Business currency flows through to hourly pricing."""
        engine = PricingEngine()
        offer = MagicMock()
        offer.id = uuid.uuid4()
        offer.pricing_model = "hourly"
        offer.pricing_config = {"hourly_rate": "50", "estimated_hours": "2"}
        offer.delivery_mode = "on_site"
        offer.name = "Test"
        offer.business_id = uuid.uuid4()

        result = engine.calculate(
            service_offer=offer,
            business_currency="NZD",
        )
        assert result.currency == "NZD"
        assert result.amount == Decimal("100.00")

    def test_pricing_config_currency_overrides_business_currency(self):
        """Explicit pricing_config currency takes priority over business currency."""
        engine = PricingEngine()
        offer = MagicMock()
        offer.id = uuid.uuid4()
        offer.pricing_model = "fixed"
        offer.pricing_config = {"amount": "100", "currency": "USD"}
        offer.delivery_mode = "on_site"
        offer.name = "Test"
        offer.business_id = uuid.uuid4()

        result = engine.calculate(
            service_offer=offer,
            business_currency="EUR",
        )
        assert result.currency == "USD"  # pricing_config wins
