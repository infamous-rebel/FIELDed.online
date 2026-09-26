"""Deterministic Fee Calculator.

Given a CommercialPolicy and a transaction amount, computes the
FIELDed platform fee.  The calculator is a pure function — no
database access, no side effects, independently testable.

The calculator NEVER:
- Merges Stripe processing fees into the platform fee
- Consults AI for fee decisions
- Mutates state

Stripe processing fees are external Stripe charges and remain
separately identified.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.domain.commercial_policy.models import CommercialPolicy
from app.logging import get_logger

logger = get_logger(__name__)

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class FeeResult:
    """Deterministic fee calculation output.

    Immutable — the result is a point-in-time snapshot that can be
    stored as fee_evidence on a transaction.
    """

    customer_amount: Decimal
    platform_fee: Decimal
    fee_type: str
    percentage_applied: Decimal
    fixed_applied: Decimal
    business_proceeds: Decimal
    currency: str

    # Policy identification
    policy_id: uuid.UUID
    policy_name: str
    policy_scope: str
    policy_version: int

    # Effective dates
    effective_from: datetime
    effective_until: datetime | None

    # Display
    disclosure: str | None = None

    def to_evidence_dict(self) -> dict[str, Any]:
        """Serialize for storage in transaction fee_evidence JSONB."""
        return {
            "customer_amount": str(self.customer_amount),
            "platform_fee": str(self.platform_fee),
            "fee_type": self.fee_type,
            "percentage_applied": str(self.percentage_applied),
            "fixed_applied": str(self.fixed_applied),
            "business_proceeds": str(self.business_proceeds),
            "currency": self.currency,
            "policy_id": str(self.policy_id),
            "policy_name": self.policy_name,
            "policy_scope": self.policy_scope,
            "policy_version": self.policy_version,
            "effective_from": self.effective_from.isoformat(),
            "effective_until": self.effective_until.isoformat() if self.effective_until else None,
            "disclosure": self.disclosure,
            "stripe_note": "Stripe processing fees apply separately and are not included in the platform fee.",
        }


class FeeCalculator:
    """Pure deterministic fee calculator.

    Usage:
        calc = FeeCalculator()
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")
    """

    def calculate(
        self,
        policy: CommercialPolicy,
        *,
        amount: Decimal,
        currency: str,
    ) -> FeeResult:
        """Calculate the FIELDed platform fee for a transaction.

        Args:
            policy: The applicable commercial policy.
            amount: The transaction (service) amount.  Must be >= 0.
            currency: ISO 4217 currency code.

        Returns:
            FeeResult with deterministic fee breakdown.

        Raises:
            ValueError: If the policy is invalid or amount is negative.
        """
        if amount < Decimal("0"):
            raise ValueError(f"Transaction amount must be non-negative, got {amount}")

        fee_type = policy.fee_type
        percentage = Decimal(str(policy.percentage))
        fixed = Decimal(str(policy.fixed_amount))

        # Validate fee_type / component consistency
        if fee_type == "percentage" and (percentage < Decimal("0") or percentage > Decimal("100")):
            raise ValueError(f"Percentage must be 0–100, got {percentage}")
        if fee_type == "fixed" and fixed < Decimal("0"):
            raise ValueError(f"Fixed amount must be non-negative, got {fixed}")
        if fee_type == "combined":
            if percentage < Decimal("0") or percentage > Decimal("100"):
                raise ValueError(f"Combined percentage must be 0–100, got {percentage}")
            if fixed < Decimal("0"):
                raise ValueError(f"Combined fixed amount must be non-negative, got {fixed}")

        # Calculate fee
        pct_component = Decimal("0")
        fix_component = Decimal("0")

        if fee_type == "percentage":
            pct_component = (amount * percentage / Decimal("100")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        elif fee_type == "fixed":
            fix_component = fixed.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        elif fee_type == "combined":
            pct_component = (amount * percentage / Decimal("100")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            fix_component = fixed.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        elif fee_type == "zero":
            # Launch / onboarding / free-tier — fee = 0
            pct_component = Decimal("0.00")
            fix_component = Decimal("0.00")
        else:
            raise ValueError(f"Unknown fee type: {fee_type}")

        platform_fee = (pct_component + fix_component).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Fee cannot exceed the transaction amount
        if platform_fee > amount:
            platform_fee = amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        business_proceeds = (amount - platform_fee).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return FeeResult(
            customer_amount=amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            platform_fee=platform_fee,
            fee_type=fee_type,
            percentage_applied=percentage,
            fixed_applied=fix_component,
            business_proceeds=business_proceeds,
            currency=currency,
            policy_id=policy.id,
            policy_name=policy.name,
            policy_scope=policy.scope,
            policy_version=policy.version,
            effective_from=policy.effective_from,
            effective_until=policy.effective_until,
            disclosure=policy.disclosure,
        )
