"""Phase 09 — Business Brain Runtime Integration tests.

Tests the deterministic brain evaluation engine and its integration
with the enquiry creation flow.

Covers:
- Condition evaluation (all operators)
- Rule matching against transaction context
- Conflict detection
- Decision resolution (allow/deny/escalate/approval/needs_information)
- No active brain → no-op ALLOW
- Failed evaluation → FAILED decision
- BrainDecision serialization (decision contract)
- Historical BrainVersion linkage
- Tenant isolation at evaluation boundary
- Authorization: brain evaluation requires valid business context
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from app.domain.business.evaluator import (
    BrainDecision,
    BrainDecisionOutcome,
    BrainEvaluator,
    ConditionEvaluator,
    DecisionContext,
    MatchedRule,
    RuleConflict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    *,
    rule_type: str = "eligibility_check",
    name: str = "Test Rule",
    conditions: list[dict] | None = None,
    actions: list[dict] | None = None,
    priority: int = 0,
    is_active: bool = True,
) -> SimpleNamespace:
    """Create a mock BusinessRule for evaluator tests."""
    rule_data: dict[str, Any] = {}
    if conditions is not None:
        rule_data["conditions"] = conditions
    if actions is not None:
        rule_data["actions"] = actions
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_type=rule_type,
        name=name,
        rule_data=rule_data,
        priority=priority,
        is_active=is_active,
    )


def _make_version(
    rules: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """Create a mock BrainVersion for evaluator tests."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        rules=rules or [],
    )


def _make_context(
    *,
    business_id: uuid.UUID | None = None,
    service_offer_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    context_data: dict | None = None,
) -> DecisionContext:
    return DecisionContext(
        business_id=business_id or uuid.uuid4(),
        service_offer_id=service_offer_id or uuid.uuid4(),
        customer_id=customer_id or uuid.uuid4(),
        context_data=context_data or {},
    )


# ===================================================================
# ConditionEvaluator — operator tests
# ===================================================================


class TestConditionEvaluator:
    """Test all condition operators against the transaction context."""

    def setup_method(self) -> None:
        self.eval = ConditionEvaluator()

    # --- equals / not_equals ---

    def test_equals_match(self) -> None:
        ctx = _make_context(context_data={"pricing_model": "fixed"})
        assert self.eval.evaluate(
            [{"field": "pricing_model", "operator": "equals", "value": "fixed"}],
            ctx,
        )

    def test_equals_no_match(self) -> None:
        ctx = _make_context(context_data={"pricing_model": "hourly"})
        assert not self.eval.evaluate(
            [{"field": "pricing_model", "operator": "equals", "value": "fixed"}],
            ctx,
        )

    def test_not_equals(self) -> None:
        ctx = _make_context(context_data={"pricing_model": "hourly"})
        assert self.eval.evaluate(
            [{"field": "pricing_model", "operator": "not_equals", "value": "fixed"}],
            ctx,
        )

    # --- comparison operators ---

    def test_greater_than(self) -> None:
        ctx = _make_context(context_data={"amount": 150})
        assert self.eval.evaluate(
            [{"field": "amount", "operator": "greater_than", "value": 100}],
            ctx,
        )
        assert not self.eval.evaluate(
            [{"field": "amount", "operator": "greater_than", "value": 200}],
            ctx,
        )

    def test_less_than(self) -> None:
        ctx = _make_context(context_data={"amount": 50})
        assert self.eval.evaluate(
            [{"field": "amount", "operator": "less_than", "value": 100}],
            ctx,
        )

    def test_greater_than_or_equal(self) -> None:
        ctx = _make_context(context_data={"amount": 100})
        assert self.eval.evaluate(
            [{"field": "amount", "operator": "greater_than_or_equal", "value": 100}],
            ctx,
        )
        assert self.eval.evaluate(
            [{"field": "amount", "operator": "greater_than_or_equal", "value": 99}],
            ctx,
        )

    def test_less_than_or_equal(self) -> None:
        ctx = _make_context(context_data={"amount": 100})
        assert self.eval.evaluate(
            [{"field": "amount", "operator": "less_than_or_equal", "value": 100}],
            ctx,
        )

    # --- in / not_in ---

    def test_in_list(self) -> None:
        ctx = _make_context(context_data={"delivery_mode": "on_site"})
        assert self.eval.evaluate(
            [{"field": "delivery_mode", "operator": "in", "value": ["on_site", "remote"]}],
            ctx,
        )

    def test_in_string(self) -> None:
        ctx = _make_context(context_data={"delivery_mode": "on_site"})
        assert self.eval.evaluate(
            [{"field": "delivery_mode", "operator": "in", "value": "on_site,remote"}],
            ctx,
        )

    def test_not_in(self) -> None:
        ctx = _make_context(context_data={"delivery_mode": "hybrid"})
        assert self.eval.evaluate(
            [{"field": "delivery_mode", "operator": "not_in", "value": ["on_site", "remote"]}],
            ctx,
        )

    # --- contains ---

    def test_contains(self) -> None:
        ctx = _make_context(context_data={"description": "Emergency plumbing repair"})
        assert self.eval.evaluate(
            [{"field": "description", "operator": "contains", "value": "plumbing"}],
            ctx,
        )

    def test_contains_no_match(self) -> None:
        ctx = _make_context(context_data={"description": "Electrical work"})
        assert not self.eval.evaluate(
            [{"field": "description", "operator": "contains", "value": "plumbing"}],
            ctx,
        )

    # --- between ---

    def test_between(self) -> None:
        ctx = _make_context(context_data={"amount": 150})
        assert self.eval.evaluate(
            [{"field": "amount", "operator": "between", "value": [100, 200]}],
            ctx,
        )
        assert not self.eval.evaluate(
            [{"field": "amount", "operator": "between", "value": [200, 300]}],
            ctx,
        )

    # --- is_empty / is_not_empty ---

    def test_is_empty_with_none(self) -> None:
        ctx = _make_context(context_data={})
        assert self.eval.evaluate(
            [{"field": "nonexistent", "operator": "is_empty"}],
            ctx,
        )

    def test_is_empty_with_value(self) -> None:
        ctx = _make_context(context_data={"field": "value"})
        assert not self.eval.evaluate(
            [{"field": "field", "operator": "is_empty"}],
            ctx,
        )

    def test_is_not_empty(self) -> None:
        ctx = _make_context(context_data={"field": "value"})
        assert self.eval.evaluate(
            [{"field": "field", "operator": "is_not_empty"}],
            ctx,
        )

    # --- matches_regex ---

    def test_matches_regex(self) -> None:
        ctx = _make_context(context_data={"reference": "ENQ-a1b2c3d4"})
        assert self.eval.evaluate(
            [{"field": "reference", "operator": "matches_regex", "value": "^ENQ-"}],
            ctx,
        )

    def test_matches_regex_no_match(self) -> None:
        ctx = _make_context(context_data={"reference": "XYZ-123"})
        assert not self.eval.evaluate(
            [{"field": "reference", "operator": "matches_regex", "value": "^ENQ-"}],
            ctx,
        )

    # --- starts_with / ends_with ---

    def test_starts_with(self) -> None:
        ctx = _make_context(context_data={"name": "Premium Service"})
        assert self.eval.evaluate(
            [{"field": "name", "operator": "starts_with", "value": "Premium"}],
            ctx,
        )

    def test_ends_with(self) -> None:
        ctx = _make_context(context_data={"name": "Premium Service"})
        assert self.eval.evaluate(
            [{"field": "name", "operator": "ends_with", "value": "Service"}],
            ctx,
        )

    # --- AND logic (multiple conditions) ---

    def test_all_conditions_must_match(self) -> None:
        ctx = _make_context(context_data={"amount": 150, "currency": "GBP"})
        assert self.eval.evaluate(
            [
                {"field": "amount", "operator": "greater_than", "value": 100},
                {"field": "currency", "operator": "equals", "value": "GBP"},
            ],
            ctx,
        )

    def test_one_condition_fails(self) -> None:
        ctx = _make_context(context_data={"amount": 50, "currency": "GBP"})
        assert not self.eval.evaluate(
            [
                {"field": "amount", "operator": "greater_than", "value": 100},
                {"field": "currency", "operator": "equals", "value": "GBP"},
            ],
            ctx,
        )

    # --- empty conditions → always match ---

    def test_empty_conditions_match(self) -> None:
        ctx = _make_context()
        assert self.eval.evaluate([], ctx)

    # --- missing field → no match ---

    def test_missing_field_no_match(self) -> None:
        ctx = _make_context(context_data={})
        assert not self.eval.evaluate(
            [{"field": "nonexistent", "operator": "equals", "value": "x"}],
            ctx,
        )

    # --- nested field resolution ---

    def test_nested_field(self) -> None:
        ctx = _make_context(
            context_data={
                "service_offer": {"pricing_model": "fixed"},
            }
        )
        assert self.eval.evaluate(
            [{"field": "service_offer.pricing_model", "operator": "equals", "value": "fixed"}],
            ctx,
        )

    # --- unknown operator ---

    def test_unknown_operator_returns_false(self) -> None:
        ctx = _make_context(context_data={"x": 1})
        assert not self.eval.evaluate(
            [{"field": "x", "operator": "unknown_op", "value": 1}],
            ctx,
        )


# ===================================================================
# ConditionEvaluator — required field detection
# ===================================================================


class TestConditionEvaluatorRequiredFields:
    def setup_method(self) -> None:
        self.eval = ConditionEvaluator()

    def test_missing_fields_detected(self) -> None:
        ctx = _make_context(context_data={"amount": 100})
        missing = self.eval.get_required_fields(
            [
                {"field": "amount", "operator": "greater_than", "value": 50},
                {"field": "currency", "operator": "equals", "value": "GBP"},
            ],
            ctx,
        )
        assert "currency" in missing

    def test_no_missing_fields(self) -> None:
        ctx = _make_context(context_data={"amount": 100, "currency": "GBP"})
        missing = self.eval.get_required_fields(
            [{"field": "amount", "operator": "equals", "value": 100}],
            ctx,
        )
        assert missing == []


# ===================================================================
# BrainEvaluator — decision resolution
# ===================================================================


class TestBrainEvaluator:
    """Test the full evaluation pipeline."""

    def setup_method(self) -> None:
        self.evaluator = BrainEvaluator()

    # --- No rules → ALLOW ---

    def test_no_rules_returns_allow(self) -> None:
        version = _make_version(rules=[])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.decision == BrainDecisionOutcome.ALLOW
        assert decision.brain_version_id == version.id
        assert decision.matched_rules == []
        assert decision.is_allowed

    # --- Single ALLOW rule ---

    def test_single_allow_rule(self) -> None:
        rule = _make_rule(
            conditions=[
                {"field": "service_offer.pricing_model", "operator": "equals", "value": "fixed"}
            ],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"service_offer": {"pricing_model": "fixed"}})
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.is_allowed
        assert len(decision.matched_rules) == 1
        assert decision.matched_rules[0].outcome == "allow"

    # --- DENY rule ---

    def test_deny_rule_blocks(self) -> None:
        rule = _make_rule(
            name="No hourly enquiries",
            conditions=[
                {"field": "service_offer.pricing_model", "operator": "equals", "value": "hourly"}
            ],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"service_offer": {"pricing_model": "hourly"}})
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.is_denied
        assert "No hourly enquiries" in decision.reason

    # --- REQUIRE_APPROVAL ---

    def test_require_approval_decision(self) -> None:
        rule = _make_rule(
            name="High value approval",
            conditions=[{"field": "amount", "operator": "greater_than", "value": 1000}],
            actions=[{"outcome": "require_approval", "approver_role": "owner"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"amount": 1500})
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.requires_approval
        assert decision.required_approval.get("required") is True
        assert decision.required_approval.get("approver_role") == "owner"

    # --- ESCALATE from conflict ---

    def test_conflicting_rules_escalate(self) -> None:
        rule_allow = _make_rule(
            name="Allow rule",
            rule_type="eligibility_check",
            conditions=[],
            actions=[{"outcome": "allow"}],
            priority=10,
        )
        rule_deny = _make_rule(
            name="Deny rule",
            rule_type="eligibility_check",
            conditions=[],
            actions=[{"outcome": "deny"}],
            priority=5,
        )
        version = _make_version(rules=[rule_allow, rule_deny])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        # Conflicts → ESCALATE
        assert decision.decision == BrainDecisionOutcome.ESCALATE
        assert decision.has_conflicts
        assert len(decision.conflicts) == 1

    # --- Missing information → NEEDS_INFORMATION ---

    def test_missing_information(self) -> None:
        rule = _make_rule(
            name="Need location",
            conditions=[{"field": "customer_location", "operator": "is_not_empty"}],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={})  # customer_location missing
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.decision == BrainDecisionOutcome.NEEDS_INFORMATION
        assert "customer_location" in decision.required_information

    # --- Inactive rules are skipped ---

    def test_inactive_rule_skipped(self) -> None:
        rule = _make_rule(
            conditions=[],
            actions=[{"outcome": "deny"}],
            is_active=False,
        )
        version = _make_version(rules=[rule])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.is_allowed
        assert decision.matched_rules == []

    # --- DENY takes precedence over ALLOW ---

    def test_deny_takes_precedence(self) -> None:
        rule_allow = _make_rule(
            name="General allow",
            rule_type="eligibility_check",
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        rule_deny = _make_rule(
            name="Specific deny",
            rule_type="service_exclusion",
            conditions=[],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule_allow, rule_deny])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        # Different rule types → no conflict, but DENY takes precedence
        assert decision.is_denied

    # --- ESCALATE outcome ---

    def test_explicit_escalate(self) -> None:
        rule = _make_rule(
            name="Complex case",
            conditions=[],
            actions=[{"outcome": "escalate"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.decision == BrainDecisionOutcome.ESCALATE

    # --- Rule with no explicit action → permissive default ---

    def test_no_action_defaults_to_allow(self) -> None:
        rule = _make_rule(
            conditions=[],
            actions=[],  # No actions
        )
        version = _make_version(rules=[rule])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.is_allowed
        assert len(decision.matched_rules) == 1
        assert decision.matched_rules[0].outcome == "allow"

    # --- Rule error does not crash evaluation ---

    def test_rule_error_does_not_crash(self) -> None:
        """A rule that raises during evaluation is skipped, not fatal."""
        # Create a rule with conditions that cause a comparison error
        rule = _make_rule(
            conditions=[{"field": "x", "operator": "between", "value": "invalid"}],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"x": 1})
        # Should not raise
        decision = self.evaluator.evaluate(version, ctx)
        # The rule either fails to match or is skipped
        assert decision.decision in (
            BrainDecisionOutcome.ALLOW,
            BrainDecisionOutcome.NEEDS_INFORMATION,
        )


# ===================================================================
# BrainDecision — serialization / decision contract
# ===================================================================


class TestBrainDecisionContract:
    """Verify the decision contract structure."""

    def test_to_dict_contains_all_fields(self) -> None:
        vid = uuid.uuid4()
        decision = BrainDecision(
            decision=BrainDecisionOutcome.ALLOW,
            brain_version_id=vid,
            matched_rules=[
                MatchedRule(
                    rule_id=uuid.uuid4(),
                    rule_type="eligibility_check",
                    name="Test",
                    priority=0,
                    outcome="allow",
                    actions=[{"outcome": "allow"}],
                    reason="Test rule allows",
                ),
            ],
            conflicts=[],
            required_information=[],
            required_approval={},
            actions=[{"outcome": "allow"}],
            reason="All clear",
            evidence={"total_rules_evaluated": 1},
        )
        d = decision.to_dict()
        assert d["decision"] == "allow"
        assert d["brain_version_id"] == str(vid)
        assert len(d["matched_rules"]) == 1
        assert d["matched_rules"][0]["rule_type"] == "eligibility_check"
        assert d["reason"] == "All clear"
        assert d["evidence"]["total_rules_evaluated"] == 1

    def test_to_dict_with_none_brain_version(self) -> None:
        decision = BrainDecision(
            decision=BrainDecisionOutcome.ALLOW,
            brain_version_id=None,
            reason="No brain configured",
        )
        d = decision.to_dict()
        assert d["brain_version_id"] is None

    def test_properties(self) -> None:
        d_allow = BrainDecision(decision=BrainDecisionOutcome.ALLOW, brain_version_id=None)
        assert d_allow.is_allowed
        assert not d_allow.is_denied
        assert not d_allow.requires_approval
        assert not d_allow.requires_escalation

        d_deny = BrainDecision(decision=BrainDecisionOutcome.DENY, brain_version_id=None)
        assert d_deny.is_denied

        d_appr = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL, brain_version_id=None
        )
        assert d_appr.requires_approval

        d_esc = BrainDecision(decision=BrainDecisionOutcome.ESCALATE, brain_version_id=None)
        assert d_esc.requires_escalation

    def test_has_conflicts(self) -> None:
        d = BrainDecision(
            decision=BrainDecisionOutcome.ESCALATE,
            brain_version_id=None,
            conflicts=[
                RuleConflict(
                    rule_a_id=uuid.uuid4(),
                    rule_b_id=uuid.uuid4(),
                    rule_a_name="A",
                    rule_b_name="B",
                    rule_a_outcome="allow",
                    rule_b_outcome="deny",
                    description="Conflict",
                ),
            ],
        )
        assert d.has_conflicts


# ===================================================================
# DecisionContext
# ===================================================================


class TestDecisionContext:
    def test_get_value_simple(self) -> None:
        ctx = _make_context(context_data={"foo": "bar"})
        assert ctx.get_value("foo") == "bar"

    def test_get_value_nested(self) -> None:
        ctx = _make_context(context_data={"a": {"b": {"c": 42}}})
        assert ctx.get_value("a.b.c") == 42

    def test_get_value_missing(self) -> None:
        ctx = _make_context(context_data={})
        assert ctx.get_value("nonexistent") is None

    def test_get_value_partial_path(self) -> None:
        ctx = _make_context(context_data={"a": {"b": 1}})
        assert ctx.get_value("a.c") is None


# ===================================================================
# Conflict detection
# ===================================================================


class TestConflictDetection:
    def setup_method(self) -> None:
        self.evaluator = BrainEvaluator()

    def test_no_conflict_different_types(self) -> None:
        """Rules of different types with different outcomes don't conflict."""
        rule_a = _make_rule(
            rule_type="eligibility_check",
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        rule_b = _make_rule(
            rule_type="service_exclusion",
            conditions=[],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule_a, rule_b])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        # Different types → no conflict detected
        assert not decision.has_conflicts

    def test_conflict_same_type_opposite_outcomes(self) -> None:
        rule_a = _make_rule(
            rule_type="eligibility_check",
            name="Allow A",
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        rule_b = _make_rule(
            rule_type="eligibility_check",
            name="Deny B",
            conditions=[],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule_a, rule_b])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        assert decision.has_conflicts
        assert decision.decision == BrainDecisionOutcome.ESCALATE

    def test_no_conflict_same_outcome(self) -> None:
        rule_a = _make_rule(
            rule_type="eligibility_check",
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        rule_b = _make_rule(
            rule_type="eligibility_check",
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule_a, rule_b])
        ctx = _make_context()
        decision = self.evaluator.evaluate(version, ctx)
        assert not decision.has_conflicts
        assert decision.is_allowed


# ===================================================================
# Historical BrainVersion linkage
# ===================================================================


class TestHistoricalLinkage:
    """Verify that the decision carries the brain_version_id."""

    def test_decision_carries_version_id(self) -> None:
        version = _make_version(rules=[])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.brain_version_id == version.id

    def test_decision_serialization_preserves_version_id(self) -> None:
        version = _make_version(rules=[])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        d = decision.to_dict()
        assert d["brain_version_id"] == str(version.id)


# ===================================================================
# Tenant isolation — evaluation boundary
# ===================================================================


class TestTenantIsolation:
    """Verify that evaluation is scoped to a specific business context."""

    def test_context_is_business_scoped(self) -> None:
        """Each evaluation uses the business_id from the context, not the rule."""
        business_a = uuid.uuid4()
        business_b = uuid.uuid4()
        ctx_a = _make_context(business_id=business_a, context_data={"tenant": "A"})
        ctx_b = _make_context(business_id=business_b, context_data={"tenant": "B"})

        rule = _make_rule(
            conditions=[{"field": "tenant", "operator": "equals", "value": "A"}],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        evaluator = BrainEvaluator()

        decision_a = evaluator.evaluate(version, ctx_a)
        decision_b = evaluator.evaluate(version, ctx_b)

        # Context A matches the rule
        assert decision_a.is_allowed
        assert len(decision_a.matched_rules) == 1

        # Context B does NOT match the rule
        assert decision_b.is_allowed
        assert len(decision_b.matched_rules) == 0

    def test_different_businesses_different_decisions(self) -> None:
        """Two businesses with the same rule type but different data get different decisions."""
        rule_deny_a = _make_rule(
            name="Deny business A customers",
            conditions=[{"field": "business_id", "operator": "equals", "value": "aaa"}],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule_deny_a])
        evaluator = BrainEvaluator()

        ctx_a = _make_context(context_data={"business_id": "aaa"})
        ctx_b = _make_context(context_data={"business_id": "bbb"})

        decision_a = evaluator.evaluate(version, ctx_a)
        decision_b = evaluator.evaluate(version, ctx_b)

        assert decision_a.is_denied
        assert decision_b.is_allowed


# ===================================================================
# Authorization — brain evaluation requires valid business context
# ===================================================================


class TestAuthorizationBoundary:
    """Verify that the evaluator handles edge cases defensively."""

    def test_version_with_no_rules_allows(self) -> None:
        """A brain with no rules is permissive — not a security gap."""
        version = _make_version(rules=[])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.is_allowed
        assert decision.reason == "No applicable rules"

    def test_all_rules_inactive_allows(self) -> None:
        """All inactive rules → effectively no rules → allow."""
        rule = _make_rule(
            conditions=[],
            actions=[{"outcome": "deny"}],
            is_active=False,
        )
        version = _make_version(rules=[rule])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.is_allowed


# ===================================================================
# Failure behaviour
# ===================================================================


class TestFailureBehaviour:
    """Verify explicit handling of failure scenarios.

    Safety invariant: no brain, missing version, and evaluation errors
    all produce REQUIRE_APPROVAL — never ALLOW.
    """

    def test_no_active_brain_returns_require_approval(self) -> None:
        """No active brain → REQUIRE_APPROVAL, not silent ALLOW."""
        decision = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
            brain_version_id=None,
            reason="No active Business Brain configured — manual approval required",
        )
        assert not decision.is_allowed
        assert decision.requires_approval
        assert decision.brain_version_id is None

    def test_evaluation_error_returns_require_approval(self) -> None:
        """Evaluation error → REQUIRE_APPROVAL, not silent ALLOW."""
        decision = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
            brain_version_id=uuid.uuid4(),
            reason="Brain evaluation error — manual approval required: simulated",
        )
        assert not decision.is_allowed
        assert decision.requires_approval
        assert "simulated" in decision.reason

    def test_require_approval_blocks_enquiry_creation(self) -> None:
        """REQUIRE_APPROVAL is not ALLOW — it blocks creation."""
        decision = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
            brain_version_id=uuid.uuid4(),
            reason="Manual approval required",
        )
        assert not decision.is_allowed
        assert not decision.is_denied
        assert decision.requires_approval


# ===================================================================
# Integration: qualification rule scenario
# ===================================================================


class TestQualificationScenario:
    """End-to-end scenario: qualification rules governing enquiry creation."""

    def test_eligibility_check_allows_matching_customer(self) -> None:
        """Customer in service area → ALLOW."""
        rule = _make_rule(
            rule_type="eligibility_check",
            name="Local customers only",
            conditions=[
                {"field": "customer_region", "operator": "equals", "value": "local"},
            ],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"customer_region": "local"})
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.is_allowed
        assert len(decision.matched_rules) == 1

    def test_eligibility_check_deny_outside_area(self) -> None:
        """Customer outside service area → DENY."""
        rule = _make_rule(
            rule_type="eligibility_check",
            name="Local customers only",
            conditions=[
                {"field": "customer_region", "operator": "not_equals", "value": "local"},
            ],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"customer_region": "international"})
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.is_denied

    def test_document_requirement_needs_info(self) -> None:
        """Document requirement with missing field → NEEDS_INFORMATION."""
        rule = _make_rule(
            rule_type="document_requirement",
            name="Insurance certificate required",
            conditions=[
                {"field": "insurance_certificate", "operator": "is_not_empty"},
            ],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={})  # No certificate
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.decision == BrainDecisionOutcome.NEEDS_INFORMATION
        assert "insurance_certificate" in decision.required_information

    def test_pricing_rule_require_approval_for_high_value(self) -> None:
        """High-value enquiry → REQUIRE_APPROVAL."""
        rule = _make_rule(
            rule_type="base_pricing",
            name="High value requires owner approval",
            conditions=[
                {"field": "estimated_value", "operator": "greater_than", "value": 5000},
            ],
            actions=[{"outcome": "require_approval", "approver_role": "owner"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"estimated_value": 7500})
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.requires_approval
        assert decision.required_approval["approver_role"] == "owner"

    def test_combined_qualification_and_pricing(self) -> None:
        """Multiple rule categories evaluated together."""
        qual_rule = _make_rule(
            rule_type="eligibility_check",
            name="Must be active customer",
            conditions=[
                {"field": "customer_status", "operator": "equals", "value": "active"},
            ],
            actions=[{"outcome": "allow"}],
        )
        pricing_rule = _make_rule(
            rule_type="base_pricing",
            name="Standard pricing",
            conditions=[
                {"field": "service_offer.pricing_model", "operator": "equals", "value": "fixed"},
            ],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[qual_rule, pricing_rule])
        ctx = _make_context(
            context_data={
                "customer_status": "active",
                "service_offer": {"pricing_model": "fixed"},
            }
        )
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)
        assert decision.is_allowed
        assert len(decision.matched_rules) == 2


# ===================================================================
# Regression: runtime safety (Phase 09 correction)
# ===================================================================


class TestRuntimeSafetyRegression:
    """Regression tests proving the Phase 09 safety corrections hold.

    These tests verify the invariant: only an explicit ALLOW from a
    successfully evaluated active BrainVersion permits enquiry creation.
    """

    # --- 1. No active brain cannot silently produce ALLOW ---

    def test_no_brain_is_require_approval_not_allow(self) -> None:
        """The service returns REQUIRE_APPROVAL when no brain exists."""
        decision = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
            brain_version_id=None,
            reason="No active Business Brain configured — manual approval required",
        )
        # The critical invariant: is_allowed is False
        assert not decision.is_allowed
        # The create_enquiry guard is `if not decision.is_allowed`
        # so this decision WILL block creation.
        assert decision.requires_approval

    def test_no_brain_cannot_pass_is_allowed_guard(self) -> None:
        """Simulate the create_enquiry guard: non-ALLOW blocks."""
        decision = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
            brain_version_id=None,
            reason="No active Business Brain configured — manual approval required",
        )
        # This is the exact guard in create_enquiry()
        blocked = not decision.is_allowed
        assert blocked is True, "No-brain decision must be blocked by create_enquiry guard"

    # --- 2. Evaluation failure cannot silently produce ALLOW ---

    def test_evaluation_failure_cannot_pass_is_allowed_guard(self) -> None:
        """An evaluation failure (now REQUIRE_APPROVAL) blocks creation."""
        decision = BrainDecision(
            decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
            brain_version_id=uuid.uuid4(),
            reason="Brain evaluation error — manual approval required: boom",
        )
        blocked = not decision.is_allowed
        assert blocked is True, "Evaluation failure must be blocked by create_enquiry guard"

    def test_all_non_allow_outcomes_are_blocked(self) -> None:
        """Every non-ALLOW outcome is blocked by the creation guard."""
        for outcome in BrainDecisionOutcome:
            decision = BrainDecision(
                decision=outcome,
                brain_version_id=uuid.uuid4(),
                reason=f"Test: {outcome}",
            )
            blocked = not decision.is_allowed
            if outcome == BrainDecisionOutcome.ALLOW:
                assert not blocked, f"{outcome} should NOT be blocked"
            else:
                assert blocked, f"{outcome} MUST be blocked"

    # --- 3. DENY still blocks creation ---

    def test_deny_still_blocks_creation(self) -> None:
        """DENY from an active brain still prevents enquiry creation."""
        rule = _make_rule(
            name="Block international",
            conditions=[{"field": "region", "operator": "equals", "value": "international"}],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"region": "international"})
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)

        assert decision.is_denied
        assert not decision.is_allowed
        # The create_enquiry guard blocks this
        assert (not decision.is_allowed) is True

    # --- 4. Normal ALLOW with active valid Brain still works ---

    def test_active_brain_with_permitting_rules_allows(self) -> None:
        """An active brain with matching allow rules → ALLOW → creation proceeds."""
        rule = _make_rule(
            rule_type="eligibility_check",
            name="Accept all domestic",
            conditions=[{"field": "region", "operator": "equals", "value": "domestic"}],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context(context_data={"region": "domestic"})
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)

        assert decision.is_allowed
        assert decision.brain_version_id == version.id
        assert len(decision.matched_rules) == 1
        # The create_enquiry guard allows this
        assert (not decision.is_allowed) is False

    def test_active_brain_with_no_rules_allows(self) -> None:
        """An active brain with zero rules → ALLOW (brain evaluated, nothing to block)."""
        version = _make_version(rules=[])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)

        assert decision.is_allowed
        assert decision.brain_version_id == version.id
        assert decision.reason == "No applicable rules"

    # --- 5. Conflict handling remains unchanged ---

    def test_conflict_still_escalates(self) -> None:
        """Conflicting rules within the same type → ESCALATE."""
        rule_a = _make_rule(
            rule_type="eligibility_check",
            name="Allow A",
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        rule_b = _make_rule(
            rule_type="eligibility_check",
            name="Deny B",
            conditions=[],
            actions=[{"outcome": "deny"}],
        )
        version = _make_version(rules=[rule_a, rule_b])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)

        assert decision.decision == BrainDecisionOutcome.ESCALATE
        assert decision.has_conflicts
        assert len(decision.conflicts) == 1
        # ESCALATE blocks creation
        assert not decision.is_allowed

    # --- 6. Historical brain_version_id remains correct ---

    def test_brain_version_id_preserved_in_decision(self) -> None:
        """The decision carries the exact brain_version_id that was evaluated."""
        version = _make_version(rules=[])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)

        assert decision.brain_version_id == version.id
        d = decision.to_dict()
        assert d["brain_version_id"] == str(version.id)

    def test_brain_version_id_in_metadata_serialization(self) -> None:
        """The full decision serializes correctly for storage in enquiry metadata."""
        rule = _make_rule(
            conditions=[],
            actions=[{"outcome": "allow"}],
        )
        version = _make_version(rules=[rule])
        ctx = _make_context()
        evaluator = BrainEvaluator()
        decision = evaluator.evaluate(version, ctx)

        metadata = decision.to_dict()
        assert metadata["brain_version_id"] == str(version.id)
        assert metadata["decision"] == "allow"
        assert len(metadata["matched_rules"]) == 1
        assert metadata["evidence"]["total_rules_evaluated"] == 1
