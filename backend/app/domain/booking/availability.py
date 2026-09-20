"""Deterministic availability evaluator.

Evaluates whether a requested service time is available based on
Business Brain availability rules and ServiceOffer configuration.

The Brain determines policy.  This service evaluates that policy
against a concrete datetime request.

The evaluator NEVER creates or modifies bookings.  It returns a
structured AvailabilityResult that the calling service interprets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.business.evaluator import ConditionEvaluator, DecisionContext
from app.domain.business.models import BrainVersion, BusinessRule
from app.domain.services.models import ServiceOffer
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AvailabilityResult:
    """Result of an availability evaluation."""
    available: bool
    requested_at: datetime
    reason: str = ""
    brain_version_id: uuid.UUID | None = None
    matched_rules: list[dict[str, Any]] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_evidence_dict(self) -> dict[str, Any]:
        """Serialize for storage in Booking.decision_evidence."""
        return {
            "available": self.available,
            "requested_at": self.requested_at.isoformat(),
            "reason": self.reason,
            "brain_version_id": str(self.brain_version_id) if self.brain_version_id else None,
            "matched_rules": self.matched_rules,
            "blocked_by": self.blocked_by,
        }


class AvailabilityEvaluator:
    """Evaluates availability based on Brain rules and service configuration.

    Checks (in order):
    1. Blackout periods — hard blocks
    2. Operating hours — day-of-week + time-of-day
    3. Minimum notice — advance booking requirement
    4. Maximum advance — forward booking window
    5. Capacity / concurrent limits — evaluated against existing bookings
    """

    def __init__(self) -> None:
        self._condition_eval = ConditionEvaluator()

    def evaluate(
        self,
        *,
        requested_at: datetime,
        service_offer: ServiceOffer,
        brain_version: BrainVersion | None = None,
        context: DecisionContext | None = None,
        existing_bookings: list[Any] | None = None,
    ) -> AvailabilityResult:
        """Evaluate whether the requested time is available.

        Args:
            requested_at: The requested service datetime (timezone-aware).
            service_offer: The service offer being booked.
            brain_version: Optional active BrainVersion with availability rules.
            context: Optional decision context for rule condition evaluation.
            existing_bookings: Optional list of existing bookings for capacity checks.

        Returns:
            AvailabilityResult — deterministic, traceable.
        """
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        blocked_by: list[str] = []
        matched_rules: list[dict[str, Any]] = []
        brain_version_id = brain_version.id if brain_version else None

        # If no Brain version, use service offer defaults
        if brain_version is None:
            return AvailabilityResult(
                available=True,
                requested_at=requested_at,
                reason="No Business Brain — availability allowed by default",
                brain_version_id=None,
            )

        # Collect availability rules
        availability_rules = [
            r for r in (brain_version.rules or [])
            if r.rule_type in _AVAILABILITY_RULE_TYPES and r.is_active
        ]

        for rule in availability_rules:
            try:
                rule_data = rule.rule_data or {}
                conditions = rule_data.get("conditions", [])

                # Check if rule conditions match
                if conditions and context is not None:
                    if not self._condition_eval.evaluate(conditions, context):
                        continue

                matched_rules.append({
                    "rule_id": str(rule.id),
                    "rule_type": rule.rule_type,
                    "name": rule.name,
                })

                # Evaluate the rule
                block = self._evaluate_rule(
                    rule=rule,
                    rule_data=rule_data,
                    requested_at=requested_at,
                    now=now,
                    existing_bookings=existing_bookings or [],
                )
                if block:
                    blocked_by.append(f"{rule.name} ({rule.rule_type})")

            except Exception:
                logger.exception(
                    "availability_rule_evaluation_error",
                    rule_id=str(rule.id),
                    rule_type=rule.rule_type,
                )
                # A single rule failure must not crash the evaluation.

        available = len(blocked_by) == 0
        reason = (
            "All availability rules permit this time"
            if available
            else f"Blocked by: {'; '.join(blocked_by)}"
        )

        return AvailabilityResult(
            available=available,
            requested_at=requested_at,
            reason=reason,
            brain_version_id=brain_version_id,
            matched_rules=matched_rules,
            blocked_by=blocked_by,
            evidence={
                "total_rules_evaluated": len(availability_rules),
                "blocked_count": len(blocked_by),
            },
        )

    def _evaluate_rule(
        self,
        *,
        rule: BusinessRule,
        rule_data: dict[str, Any],
        requested_at: datetime,
        now: datetime,
        existing_bookings: list[Any],
    ) -> bool:
        """Evaluate a single availability rule. Returns True if BLOCKED."""
        rule_type = rule.rule_type

        if rule_type == "blackout_period":
            return self._check_blackout(rule_data, requested_at)

        if rule_type == "operating_hours":
            return self._check_operating_hours(rule_data, requested_at)

        if rule_type == "minimum_notice":
            return self._check_minimum_notice(rule_data, requested_at, now)

        if rule_type == "maximum_advance":
            return self._check_maximum_advance(rule_data, requested_at, now)

        if rule_type == "capacity_limit":
            return self._check_capacity(rule_data, requested_at, existing_bookings)

        if rule_type == "concurrent_limit":
            return self._check_concurrent(rule_data, requested_at, existing_bookings)

        if rule_type == "slot_configuration":
            # Informational — slot duration/buffer configuration
            return False

        return False

    @staticmethod
    def _check_blackout(rule_data: dict[str, Any], requested_at: datetime) -> bool:
        """Check if the requested time falls in a blackout period."""
        try:
            start = _parse_datetime(rule_data.get("start_date"))
            end = _parse_datetime(rule_data.get("end_date"))
            if start is None or end is None:
                return False
            return start <= requested_at <= end
        except Exception:
            return False

    @staticmethod
    def _check_operating_hours(rule_data: dict[str, Any], requested_at: datetime) -> bool:
        """Check if the requested time is within operating hours.

        Returns True if BLOCKED (outside operating hours).
        """
        day_of_week = rule_data.get("day_of_week", "")
        open_time = rule_data.get("open_time", "")
        close_time = rule_data.get("close_time", "")

        if not day_of_week or not open_time or not close_time:
            return False

        # Map day names to weekday numbers (Monday=0)
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        expected_day = day_map.get(str(day_of_week).lower())
        if expected_day is None:
            return False

        # Check if the requested day matches
        if requested_at.weekday() != expected_day:
            return False  # Rule doesn't apply to this day

        # Check time window
        try:
            open_h, open_m = map(int, str(open_time).split(":"))
            close_h, close_m = map(int, str(close_time).split(":"))
            request_minutes = requested_at.hour * 60 + requested_at.minute
            open_minutes = open_h * 60 + open_m
            close_minutes = close_h * 60 + close_m

            # Check break times
            break_start = rule_data.get("break_start")
            break_end = rule_data.get("break_end")
            if break_start and break_end:
                try:
                    bs_h, bs_m = map(int, str(break_start).split(":"))
                    be_h, be_m = map(int, str(break_end).split(":"))
                    break_start_min = bs_h * 60 + bs_m
                    break_end_min = be_h * 60 + be_m
                    if break_start_min <= request_minutes <= break_end_min:
                        return True  # During break — blocked
                except (ValueError, TypeError):
                    pass

            if request_minutes < open_minutes or request_minutes > close_minutes:
                return True  # Outside hours — blocked

        except (ValueError, TypeError):
            return False

        return False

    @staticmethod
    def _check_minimum_notice(
        rule_data: dict[str, Any], requested_at: datetime, now: datetime
    ) -> bool:
        """Check if minimum notice period is satisfied. Returns True if BLOCKED."""
        notice_hours = rule_data.get("notice_hours")
        if notice_hours is None:
            return False
        try:
            required_notice = timedelta(hours=float(notice_hours))
            return (requested_at - now) < required_notice
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _check_maximum_advance(
        rule_data: dict[str, Any], requested_at: datetime, now: datetime
    ) -> bool:
        """Check if the booking is within the allowed advance window. Returns True if BLOCKED."""
        advance_days = rule_data.get("advance_days")
        if advance_days is None:
            return False
        try:
            max_advance = timedelta(days=float(advance_days))
            return (requested_at - now) > max_advance
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _check_capacity(
        rule_data: dict[str, Any],
        requested_at: datetime,
        existing_bookings: list[Any],
    ) -> bool:
        """Check capacity limit for a time window. Returns True if BLOCKED."""
        max_capacity = rule_data.get("max_capacity")
        if max_capacity is None:
            return False
        try:
            max_cap = int(max_capacity)
            window_minutes = int(rule_data.get("time_window_minutes", 60))
            window_start = requested_at - timedelta(minutes=window_minutes / 2)
            window_end = requested_at + timedelta(minutes=window_minutes / 2)

            count = 0
            for booking in existing_bookings:
                booking_time = getattr(booking, "requested_at", None)
                if booking_time and window_start <= booking_time <= window_end:
                    status = getattr(booking, "status", "")
                    if status not in ("cancelled", "declined", "expired"):
                        count += 1

            return count >= max_cap
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _check_concurrent(
        rule_data: dict[str, Any],
        requested_at: datetime,
        existing_bookings: list[Any],
    ) -> bool:
        """Check concurrent booking limit. Returns True if BLOCKED."""
        max_concurrent = rule_data.get("max_concurrent")
        if max_concurrent is None:
            return False
        try:
            max_conc = int(max_concurrent)
            # Count bookings at the exact same time
            count = 0
            for booking in existing_bookings:
                booking_time = getattr(booking, "requested_at", None)
                if booking_time and booking_time.date() == requested_at.date():
                    booking_hour = getattr(booking_time, "hour", None)
                    if booking_hour == requested_at.hour:
                        status = getattr(booking, "status", "")
                        if status not in ("cancelled", "declined", "expired"):
                            count += 1
            return count >= max_conc
        except (ValueError, TypeError):
            return False


def _parse_datetime(value: Any) -> datetime | None:
    """Parse a datetime string to a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# Availability rule types recognized by the evaluator
_AVAILABILITY_RULE_TYPES = frozenset({
    "operating_hours",
    "minimum_notice",
    "maximum_advance",
    "capacity_limit",
    "blackout_period",
    "slot_configuration",
    "concurrent_limit",
})


# Module-level convenience instance
availability_evaluator = AvailabilityEvaluator()
