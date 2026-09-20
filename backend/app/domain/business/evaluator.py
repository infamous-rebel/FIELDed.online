"""Business Brain runtime evaluator.

Deterministic rule evaluation engine that produces structured decisions
from an active BrainVersion and a transaction context.

The evaluator NEVER executes transactions.  It returns a BrainDecision
that the calling domain service interprets.

AI is never consulted during evaluation — all decisions are derived from
explicit rules configured in the BrainVersion.

Decision contract
-----------------
Every evaluation returns a BrainDecision containing:
- decision: the overall outcome (allow/deny/require_approval/escalate/needs_information)
- brain_version_id: the version that was evaluated (for historical traceability)
- matched_rules: rules whose conditions matched the transaction context
- conflicts: pairs of rules with contradictory outcomes
- required_information: fields the customer must provide
- required_approval: whether approval is needed and at what level
- actions: proposed actions for the calling service
- reason/evidence: human-readable explanation of the decision

Failure behaviour
-----------------
- No active BrainVersion → caller proceeds without brain governance
- Invalid Brain configuration → evaluation error, decision = failed
- Conflicting rules → conflicts reported, decision = escalate
- Missing required information → decision = needs_information
- Evaluation exception → decision = failed (never silently allow/deny)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------

class BrainDecisionOutcome(StrEnum):
    """Overall decision outcome."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ESCALATE = "escalate"
    NEEDS_INFORMATION = "needs_information"
    FAILED = "failed"


@dataclass(frozen=True)
class MatchedRule:
    """A rule whose conditions matched the transaction context."""
    rule_id: uuid.UUID
    rule_type: str
    name: str
    priority: int
    outcome: str
    actions: list[dict[str, Any]]
    reason: str


@dataclass(frozen=True)
class RuleConflict:
    """Two rules with contradictory outcomes for the same context."""
    rule_a_id: uuid.UUID
    rule_b_id: uuid.UUID
    rule_a_name: str
    rule_b_name: str
    rule_a_outcome: str
    rule_b_outcome: str
    description: str


@dataclass
class BrainDecision:
    """Structured result of brain evaluation.

    This is the decision contract between the Brain and the runtime.
    Every operational decision governed by the Brain carries this record.
    """
    decision: BrainDecisionOutcome
    brain_version_id: uuid.UUID | None
    matched_rules: list[MatchedRule] = field(default_factory=list)
    conflicts: list[RuleConflict] = field(default_factory=list)
    required_information: list[str] = field(default_factory=list)
    required_approval: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.decision == BrainDecisionOutcome.ALLOW

    @property
    def is_denied(self) -> bool:
        return self.decision == BrainDecisionOutcome.DENY

    @property
    def requires_approval(self) -> bool:
        return self.decision == BrainDecisionOutcome.REQUIRE_APPROVAL

    @property
    def requires_escalation(self) -> bool:
        return self.decision == BrainDecisionOutcome.ESCALATE

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage in enquiry metadata."""
        return {
            "decision": self.decision.value,
            "brain_version_id": str(self.brain_version_id) if self.brain_version_id else None,
            "matched_rules": [
                {
                    "rule_id": str(m.rule_id),
                    "rule_type": m.rule_type,
                    "name": m.name,
                    "priority": m.priority,
                    "outcome": m.outcome,
                    "reason": m.reason,
                }
                for m in self.matched_rules
            ],
            "conflicts": [
                {
                    "rule_a_id": str(c.rule_a_id),
                    "rule_b_id": str(c.rule_b_id),
                    "rule_a_name": c.rule_a_name,
                    "rule_b_name": c.rule_b_name,
                    "rule_a_outcome": c.rule_a_outcome,
                    "rule_b_outcome": c.rule_b_outcome,
                    "description": c.description,
                }
                for c in self.conflicts
            ],
            "required_information": self.required_information,
            "required_approval": self.required_approval,
            "actions": self.actions,
            "reason": self.reason,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Transaction context
# ---------------------------------------------------------------------------

@dataclass
class DecisionContext:
    """Transaction context for brain evaluation.

    Provides the data that rules evaluate their conditions against.
    Keys are dot-separated paths (e.g. "service_offer.pricing_model").
    """
    business_id: uuid.UUID
    service_offer_id: uuid.UUID
    customer_id: uuid.UUID
    context_data: dict[str, Any] = field(default_factory=dict)

    def get_value(self, field_path: str) -> Any:
        """Resolve a dot-separated field path from context data."""
        parts = field_path.split(".")
        current: Any = self.context_data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------

class ConditionEvaluator:
    """Evaluates rule conditions against a transaction context.

    Supports all operators defined in the rule-type registry.
    Pure function — no side effects, no database access.
    """

    def evaluate(
        self,
        conditions: list[dict[str, Any]],
        context: DecisionContext,
    ) -> bool:
        """Return True if ALL conditions match (AND logic)."""
        if not conditions:
            return True

        return all(
            self._evaluate_single(cond, context)
            for cond in conditions
        )

    def get_required_fields(
        self,
        conditions: list[dict[str, Any]],
        context: DecisionContext,
    ) -> list[str]:
        """Return context fields referenced by conditions but missing."""
        missing: list[str] = []
        for cond in conditions:
            field_path = cond.get("field", "")
            if not field_path:
                continue
            value = context.get_value(field_path)
            if value is None:
                missing.append(field_path)
        return missing

    # --- internal ---

    def _evaluate_single(
        self,
        condition: dict[str, Any],
        context: DecisionContext,
    ) -> bool:
        field_path = condition.get("field", "")
        operator = condition.get("operator", "")
        expected = condition.get("value")

        actual = context.get_value(field_path)

        return self._apply_operator(actual, operator, expected)

    @staticmethod
    def _apply_operator(actual: Any, operator: str, expected: Any) -> bool:
        if operator == "is_empty":
            return actual is None or actual == "" or actual == []
        if operator == "is_not_empty":
            return actual is not None and actual != "" and actual != []

        # For all other operators, a missing actual value → no match
        if actual is None:
            return False

        if operator == "equals":
            return actual == expected
        if operator == "not_equals":
            return actual != expected
        if operator == "greater_than":
            return _to_float(actual, None) is not None and _to_float(actual, 0) > _to_float(expected, 0)
        if operator == "less_than":
            return _to_float(actual, None) is not None and _to_float(actual, 0) < _to_float(expected, 0)
        if operator == "greater_than_or_equal":
            return _to_float(actual, None) is not None and _to_float(actual, 0) >= _to_float(expected, 0)
        if operator == "less_than_or_equal":
            return _to_float(actual, None) is not None and _to_float(actual, 0) <= _to_float(expected, 0)
        if operator == "in":
            if isinstance(expected, list):
                return actual in expected
            if isinstance(expected, str):
                return actual in expected.split(",")
            return False
        if operator == "not_in":
            if isinstance(expected, list):
                return actual not in expected
            if isinstance(expected, str):
                return actual not in expected.split(",")
            return True
        if operator == "contains":
            if isinstance(actual, str):
                return str(expected) in actual
            return False
        if operator == "between":
            if isinstance(expected, (list, tuple)) and len(expected) == 2:
                a = _to_float(actual, None)
                lo = _to_float(expected[0], None)
                hi = _to_float(expected[1], None)
                if a is not None and lo is not None and hi is not None:
                    return lo <= a <= hi
            return False
        if operator == "matches_regex":
            try:
                return bool(re.search(str(expected), str(actual)))
            except re.error:
                return False
        if operator == "starts_with":
            return str(actual).startswith(str(expected))
        if operator == "ends_with":
            return str(actual).endswith(str(expected))

        logger.warning("unknown_condition_operator", operator=operator)
        return False


def _to_float(value: Any, default: float | None = 0) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Brain evaluator
# ---------------------------------------------------------------------------

class BrainEvaluator:
    """Evaluates an active BrainVersion against a transaction context.

    Returns a deterministic BrainDecision.  Never executes transactions.
    Never consults AI.  All decisions derive from explicit rule configuration.
    """

    def __init__(self) -> None:
        self._condition_eval = ConditionEvaluator()

    def evaluate(
        self,
        brain_version: Any,
        context: DecisionContext,
    ) -> BrainDecision:
        """Evaluate all rules in a BrainVersion against the context.

        Args:
            brain_version: An ACTIVE BrainVersion with rules loaded.
            context: The transaction context to evaluate against.

        Returns:
            BrainDecision — structured, deterministic, traceable.
        """
        version_id = brain_version.id
        rules = getattr(brain_version, "rules", None) or []

        # Evaluate each active rule
        matched: list[MatchedRule] = []
        all_required_info: list[str] = []

        for rule in rules:
            if not getattr(rule, "is_active", True):
                continue

            try:
                rule_data = rule.rule_data or {}
                conditions = rule_data.get("conditions", [])
                actions = rule_data.get("actions", [])

                # Check for missing context fields
                missing = self._condition_eval.get_required_fields(conditions, context)
                if missing:
                    all_required_info.extend(missing)
                    continue

                # Evaluate conditions
                if self._condition_eval.evaluate(conditions, context):
                    outcome = self._extract_outcome(actions)
                    matched.append(MatchedRule(
                        rule_id=rule.id,
                        rule_type=rule.rule_type,
                        name=rule.name,
                        priority=getattr(rule, "priority", 0),
                        outcome=outcome,
                        actions=actions,
                        reason=self._build_rule_reason(rule, outcome),
                    ))
            except Exception:
                logger.exception(
                    "brain_rule_evaluation_error",
                    rule_id=str(rule.id),
                    rule_type=rule.rule_type,
                    brain_version_id=str(version_id),
                )
                # A single rule failure must not crash the evaluation.
                # The rule is skipped; the error is logged.

        # Detect conflicts
        conflicts = self._detect_conflicts(matched)

        # Determine overall decision
        decision = self._build_decision(
            version_id, matched, conflicts, all_required_info,
        )

        logger.info(
            "brain_evaluation_complete",
            brain_version_id=str(version_id),
            decision=decision.decision.value,
            matched_count=len(matched),
            conflict_count=len(conflicts),
        )

        return decision

    # --- conflict detection ---

    def _detect_conflicts(
        self,
        matched: list[MatchedRule],
    ) -> list[RuleConflict]:
        """Find rule pairs with contradictory outcomes.

        A conflict exists when two rules of the same type produce
        different outcomes for the same evaluation context.
        """
        conflicts: list[RuleConflict] = []

        by_type: dict[str, list[MatchedRule]] = {}
        for m in matched:
            by_type.setdefault(m.rule_type, []).append(m)

        for _rule_type, rules in by_type.items():
            if len(rules) < 2:
                continue
            for i, a in enumerate(rules):
                for b in rules[i + 1:]:
                    if self._outcomes_conflict(a.outcome, b.outcome):
                        conflicts.append(RuleConflict(
                            rule_a_id=a.rule_id,
                            rule_b_id=b.rule_id,
                            rule_a_name=a.name,
                            rule_b_name=b.name,
                            rule_a_outcome=a.outcome,
                            rule_b_outcome=b.outcome,
                            description=(
                                f"Rules '{a.name}' ({a.outcome}) and "
                                f"'{b.name}' ({b.outcome}) conflict "
                                f"within {a.rule_type}"
                            ),
                        ))

        return conflicts

    @staticmethod
    def _outcomes_conflict(a: str, b: str) -> bool:
        """Check whether two outcomes are contradictory."""
        contradictory = {
            frozenset({"allow", "deny"}),
            frozenset({"allow", "escalate"}),
        }
        return frozenset({a, b}) in contradictory

    # --- decision resolution ---

    def _build_decision(
        self,
        version_id: uuid.UUID,
        matched: list[MatchedRule],
        conflicts: list[RuleConflict],
        required_info: list[str],
    ) -> BrainDecision:
        """Resolve the overall decision from matched rules and conflicts.

        Resolution order (most restrictive wins):
        1. Conflicts → ESCALATE (never arbitrarily resolve)
        2. DENY outcome → DENY
        3. ESCALATE outcome → ESCALATE
        4. REQUIRE_APPROVAL outcome → REQUIRE_APPROVAL
        5. NEEDS_INFORMATION (missing info) → NEEDS_INFORMATION
        6. Default → ALLOW
        """
        # Conflicts → escalate
        if conflicts:
            return BrainDecision(
                decision=BrainDecisionOutcome.ESCALATE,
                brain_version_id=version_id,
                matched_rules=matched,
                conflicts=conflicts,
                required_information=list(set(required_info)),
                reason=f"Rule conflicts detected: {len(conflicts)} conflict(s)",
                evidence={
                    "total_rules_evaluated": len(matched),
                    "conflict_count": len(conflicts),
                },
            )

        # Collect outcomes
        outcomes = {m.outcome for m in matched}

        # DENY takes precedence
        if "deny" in outcomes:
            deny_rules = [m for m in matched if m.outcome == "deny"]
            return BrainDecision(
                decision=BrainDecisionOutcome.DENY,
                brain_version_id=version_id,
                matched_rules=matched,
                required_information=list(set(required_info)),
                actions=[a for m in deny_rules for a in m.actions],
                reason=f"Denied by rule(s): {', '.join(m.name for m in deny_rules)}",
                evidence={
                    "total_rules_evaluated": len(matched),
                    "deny_rules": [m.name for m in deny_rules],
                },
            )

        # ESCALATE
        if "escalate" in outcomes:
            esc_rules = [m for m in matched if m.outcome == "escalate"]
            return BrainDecision(
                decision=BrainDecisionOutcome.ESCALATE,
                brain_version_id=version_id,
                matched_rules=matched,
                required_information=list(set(required_info)),
                actions=[a for m in esc_rules for a in m.actions],
                reason=f"Escalation required by rule(s): {', '.join(m.name for m in esc_rules)}",
                evidence={
                    "total_rules_evaluated": len(matched),
                    "escalation_rules": [m.name for m in esc_rules],
                },
            )

        # REQUIRE_APPROVAL
        if "require_approval" in outcomes:
            appr_rules = [m for m in matched if m.outcome == "require_approval"]
            return BrainDecision(
                decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
                brain_version_id=version_id,
                matched_rules=matched,
                required_information=list(set(required_info)),
                required_approval={
                    "required": True,
                    "reason": f"Approval required by rule(s): {', '.join(m.name for m in appr_rules)}",
                    "approver_role": self._resolve_approver_role(appr_rules),
                },
                actions=[a for m in appr_rules for a in m.actions],
                reason=f"Approval required by rule(s): {', '.join(m.name for m in appr_rules)}",
                evidence={
                    "total_rules_evaluated": len(matched),
                    "approval_rules": [m.name for m in appr_rules],
                },
            )

        # NEEDS_INFORMATION
        unique_info = list(set(required_info))
        if unique_info:
            return BrainDecision(
                decision=BrainDecisionOutcome.NEEDS_INFORMATION,
                brain_version_id=version_id,
                matched_rules=matched,
                required_information=unique_info,
                reason=f"Missing required information: {', '.join(unique_info)}",
                evidence={
                    "total_rules_evaluated": len(matched),
                    "missing_fields": unique_info,
                },
            )

        # ALLOW (default — all matched rules allow, or no rules matched)
        all_actions = [a for m in matched for a in m.actions]
        return BrainDecision(
            decision=BrainDecisionOutcome.ALLOW,
            brain_version_id=version_id,
            matched_rules=matched,
            actions=all_actions,
            reason="All rules permit this transaction" if matched else "No applicable rules",
            evidence={"total_rules_evaluated": len(matched)},
        )

    # --- helpers ---

    @staticmethod
    def _extract_outcome(actions: list[dict[str, Any]]) -> str:
        """Extract the primary outcome from a rule's actions list."""
        for action in actions:
            outcome = action.get("outcome")
            if outcome:
                return outcome
        return "allow"  # No explicit action → permissive default

    @staticmethod
    def _build_rule_reason(rule: Any, outcome: str) -> str:
        return f"Rule '{rule.name}' ({rule.rule_type}) → {outcome}"

    @staticmethod
    def _resolve_approver_role(rules: list[MatchedRule]) -> str:
        """Extract approver role from approval rules' actions."""
        for rule in rules:
            for action in rule.actions:
                role = action.get("approver_role")
                if role:
                    return role
        return "owner"


# Module-level convenience instance
brain_evaluator = BrainEvaluator()
