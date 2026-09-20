"""Deterministic pricing engine.

Calculates quote amounts from:
1. ServiceOffer.pricing_config (base pricing)
2. Active BrainVersion pricing rules (surcharges, discounts, floors, caps)

AI is never consulted.  Every calculation is reproducible from
persisted configuration and rules.

Pricing flow:
    base_amount (from ServiceOffer or Brain base_pricing override)
    + applicable surcharges
    - applicable discounts (capped at max_discount)
    → clamped to [price_floor, price_cap]
    → clamped to minimum_charge (if set)
    → final deterministic amount
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.domain.business.evaluator import BrainEvaluator, ConditionEvaluator, DecisionContext
from app.domain.business.models import BrainVersion, BusinessRule
from app.domain.services.models import ServiceOffer
from app.logging import get_logger

logger = get_logger(__name__)

TWO_PLACES = Decimal("0.01")


@dataclass
class PricingResult:
    """Result of a deterministic pricing evaluation."""
    amount: Decimal
    currency: str
    base_amount: Decimal
    surcharges: list[dict[str, Any]] = field(default_factory=list)
    discounts: list[dict[str, Any]] = field(default_factory=list)
    floor_applied: bool = False
    cap_applied: bool = False
    minimum_charge_applied: bool = False
    quote_required: bool = False
    brain_version_id: uuid.UUID | None = None
    applied_rule_ids: list[uuid.UUID] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_evidence_dict(self) -> dict[str, Any]:
        """Serialize for storage in Quote.pricing_evidence."""
        return {
            "amount": str(self.amount),
            "currency": self.currency,
            "base_amount": str(self.base_amount),
            "surcharges": self.surcharges,
            "discounts": self.discounts,
            "floor_applied": self.floor_applied,
            "cap_applied": self.cap_applied,
            "minimum_charge_applied": self.minimum_charge_applied,
            "quote_required": self.quote_required,
            "brain_version_id": str(self.brain_version_id) if self.brain_version_id else None,
            "applied_rule_ids": [str(rid) for rid in self.applied_rule_ids],
        }


class PricingEngine:
    """Deterministic pricing calculator.

    Given a ServiceOffer and an optional BrainVersion with pricing rules,
    computes a final amount.  The result is fully reproducible from the
    persisted configuration.
    """

    def __init__(self) -> None:
        self._condition_eval = ConditionEvaluator()

    def calculate(
        self,
        *,
        service_offer: ServiceOffer,
        brain_version: BrainVersion | None = None,
        context: DecisionContext | None = None,
        business_currency: str | None = None,
    ) -> PricingResult:
        """Calculate the price for a service offer.

        Args:
            service_offer: The service offer with pricing_config.
            brain_version: Optional active BrainVersion with pricing rules.
            context: Optional decision context for rule condition evaluation.
            business_currency: The business's operational currency (ISO 4217).
                Used as fallback if pricing_config does not specify currency.

        Returns:
            PricingResult with the deterministic amount and full evidence.

        Raises:
            ValueError: If pricing configuration is invalid or missing.
        """
        pricing_config = service_offer.pricing_config or {}
        pricing_model = service_offer.pricing_model

        # 1. Resolve base amount
        base_amount, currency = self._resolve_base_amount(
            pricing_model, pricing_config, business_currency,
        )

        # Track applied rules
        applied_rules: list[uuid.UUID] = []
        surcharges: list[dict[str, Any]] = []
        discounts: list[dict[str, Any]] = []

        # 2. Apply Brain pricing rules if available
        floor_amount: Decimal | None = None
        cap_amount: Decimal | None = None
        minimum_charge: Decimal | None = None
        quote_required = False

        if brain_version is not None and context is not None:
            pricing_rules = [
                r for r in (brain_version.rules or [])
                if r.rule_type in _PRICING_RULE_TYPES and r.is_active
            ]

            for rule in pricing_rules:
                try:
                    rule_data = rule.rule_data or {}
                    conditions = rule_data.get("conditions", [])

                    # Check if rule conditions match
                    if conditions and not self._condition_eval.evaluate(conditions, context):
                        continue

                    applied_rules.append(rule.id)
                    action = self._apply_pricing_rule(
                        rule, rule_data, base_amount,
                        surcharges, discounts,
                    )

                    if action == "floor":
                        floor_amount = self._to_decimal(rule_data.get("minimum_amount"))
                    elif action == "cap":
                        cap_amount = self._to_decimal(rule_data.get("maximum_amount"))
                    elif action == "minimum_charge":
                        minimum_charge = self._to_decimal(rule_data.get("amount"))
                    elif action == "quote_required":
                        quote_required = True

                except Exception:
                    logger.exception(
                        "pricing_rule_evaluation_error",
                        rule_id=str(rule.id),
                        rule_type=rule.rule_type,
                    )
                    # A single rule failure must not crash the calculation.

        # 3. Calculate running total
        running = base_amount

        # Add surcharges
        for s in surcharges:
            running += Decimal(s["amount"])

        # Subtract discounts
        for d in discounts:
            running -= Decimal(d["amount"])

        # 4. Apply floor
        floor_applied = False
        if floor_amount is not None and running < floor_amount:
            running = floor_amount
            floor_applied = True

        # 5. Apply cap
        cap_applied = False
        if cap_amount is not None and running > cap_amount:
            running = cap_amount
            cap_applied = True

        # 6. Apply minimum charge
        minimum_charge_applied = False
        if minimum_charge is not None and running < minimum_charge:
            running = minimum_charge
            minimum_charge_applied = True

        # 7. Ensure non-negative
        if running < Decimal("0"):
            running = Decimal("0")

        # 8. Round to 2 decimal places
        amount = running.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return PricingResult(
            amount=amount,
            currency=currency,
            base_amount=base_amount,
            surcharges=surcharges,
            discounts=discounts,
            floor_applied=floor_applied,
            cap_applied=cap_applied,
            minimum_charge_applied=minimum_charge_applied,
            quote_required=quote_required,
            brain_version_id=brain_version.id if brain_version else None,
            applied_rule_ids=applied_rules,
            evidence={
                "pricing_model": pricing_model,
                "pricing_config": pricing_config,
            },
        )

    # --- Internal helpers ---

    def _resolve_base_amount(
        self,
        pricing_model: str,
        pricing_config: dict[str, Any],
        business_currency: str | None = None,
    ) -> tuple[Decimal, str]:
        """Extract the base amount and currency from the service offer's pricing config.

        Currency resolution order:
        1. Explicit currency in pricing_config (per-service offer override)
        2. business_currency (the business's operational currency)
        3. ValueError — currency must be explicitly configured somewhere
        """
        currency = pricing_config.get("currency") or business_currency
        if not currency:
            raise ValueError(
                "Currency must be configured either in the service offer's "
                "pricing_config or in the business settings."
            )

        if pricing_model == "fixed":
            amount = self._to_decimal(pricing_config.get("amount"))
            if amount is None:
                raise ValueError("Fixed pricing requires 'amount' in pricing_config")
            return amount, currency

        if pricing_model == "hourly":
            rate = self._to_decimal(pricing_config.get("hourly_rate"))
            if rate is None:
                raise ValueError("Hourly pricing requires 'hourly_rate' in pricing_config")
            hours = self._to_decimal(pricing_config.get("estimated_hours"))
            if hours is None:
                hours = Decimal("1")
            minimum_hours = self._to_decimal(pricing_config.get("minimum_hours"))
            if minimum_hours is not None and hours < minimum_hours:
                hours = minimum_hours
            return (rate * hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP), currency

        if pricing_model == "starting_at":
            amount = self._to_decimal(pricing_config.get("base_price"))
            if amount is None:
                raise ValueError("Starting-at pricing requires 'base_price' in pricing_config")
            return amount, currency

        if pricing_model == "quote_required":
            # No auto-pricing; a manual quote is required.
            # Return a placeholder base of 0 — the caller must handle this.
            return Decimal("0"), currency

        if pricing_model == "custom":
            # Custom pricing — use amount if explicitly set, otherwise 0
            amount = self._to_decimal(pricing_config.get("amount"))
            return amount or Decimal("0"), currency

        raise ValueError(f"Unknown pricing model: {pricing_model}")

    def _apply_pricing_rule(
        self,
        rule: BusinessRule,
        rule_data: dict[str, Any],
        base_amount: Decimal,
        surcharges: list[dict[str, Any]],
        discounts: list[dict[str, Any]],
    ) -> str:
        """Apply a single pricing rule and return its action type."""
        rule_type = rule.rule_type

        if rule_type == "base_pricing":
            # Override the base amount (handled by caller via return)
            return "base_override"

        if rule_type == "surcharge":
            amount = self._calculate_surcharge(rule_data, base_amount)
            if amount > Decimal("0"):
                surcharges.append({
                    "rule_id": str(rule.id),
                    "name": rule_data.get("surcharge_name", rule.name),
                    "amount": str(amount),
                    "reason": rule_data.get("reason", ""),
                })
            return "surcharge"

        if rule_type == "discount":
            amount = self._calculate_discount(rule_data, base_amount)
            if amount > Decimal("0"):
                discounts.append({
                    "rule_id": str(rule.id),
                    "name": rule_data.get("discount_name", rule.name),
                    "amount": str(amount),
                    "reason": rule_data.get("reason", ""),
                })
            return "discount"

        if rule_type == "price_floor":
            return "floor"

        if rule_type == "price_cap":
            return "cap"

        if rule_type == "quote_threshold":
            return "quote_required"

        if rule_type == "payment_terms":
            # Informational — doesn't change amount
            return "info"

        return "unknown"

    def _calculate_surcharge(
        self, rule_data: dict[str, Any], base_amount: Decimal
    ) -> Decimal:
        """Calculate a surcharge amount."""
        # Percentage-based surcharge
        percentage = self._to_decimal(rule_data.get("percentage"))
        if percentage is not None:
            return (base_amount * percentage / Decimal("100")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

        # Fixed amount surcharge
        amount = self._to_decimal(rule_data.get("amount"))
        return amount or Decimal("0")

    def _calculate_discount(
        self, rule_data: dict[str, Any], base_amount: Decimal
    ) -> Decimal:
        """Calculate a discount amount, respecting max_discount."""
        amount = Decimal("0")

        # Percentage-based discount
        percentage = self._to_decimal(rule_data.get("percentage"))
        if percentage is not None:
            amount = (base_amount * percentage / Decimal("100")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

        # Fixed amount discount
        fixed = self._to_decimal(rule_data.get("amount"))
        if fixed is not None and fixed > amount:
            amount = fixed

        # Cap the discount at max_discount
        max_discount = self._to_decimal(rule_data.get("max_discount"))
        if max_discount is not None and amount > max_discount:
            amount = max_discount

        # Discount cannot exceed the base amount
        if amount > base_amount:
            amount = base_amount

        return amount

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        """Safely convert a value to Decimal."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None


# Pricing rule types recognized by the engine
_PRICING_RULE_TYPES = frozenset({
    "base_pricing",
    "surcharge",
    "discount",
    "price_floor",
    "price_cap",
    "quote_threshold",
    "payment_terms",
})


# Module-level convenience instance
pricing_engine = PricingEngine()
