"""Business Brain rule-type registry.

Single authoritative source for which rule/configuration types are supported.
Maps rule_type strings to their metadata: category, expected shape, validator,
and schema version.

The registry is code-level (not a database table).  Adding a new rule type
requires a code change + test — this is intentional.  Runtime extensibility
of rule types is not required at this stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION = "1.0"

SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})


# ---------------------------------------------------------------------------
# Configuration categories (persisted as JSONB columns on BrainVersion)
# ---------------------------------------------------------------------------


class ConfigCategory(StrEnum):
    """Persisted configuration areas on BrainVersion."""

    SERVICE = "service"
    PRICING = "pricing"
    AVAILABILITY = "availability"
    QUALIFICATION = "qualification"
    POLICY = "policy"
    COMMUNICATION = "communication"
    ESCALATION = "escalation"
    # Conceptual classifications (not persisted as config areas):
    # BOOKING, CANCELLATION, RESCHEDULING → mapped to POLICY
    # FULFILMENT, PAYMENT, COMPLIANCE → conceptual only
    # AI_BEHAVIOUR → future ai_config
    # HUMAN_APPROVAL, INTEGRATION, GOVERNANCE → governance processes


# ---------------------------------------------------------------------------
# Condition operators (used in rule conditions)
# ---------------------------------------------------------------------------


class ConditionOperator(StrEnum):
    """Supported operators for rule conditions."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    BETWEEN = "between"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    MATCHES_REGEX = "matches_regex"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


SUPPORTED_OPERATORS: frozenset[str] = frozenset(op.value for op in ConditionOperator)


# ---------------------------------------------------------------------------
# Rule scope
# ---------------------------------------------------------------------------


class RuleScope(StrEnum):
    """Scope at which a rule applies."""

    BUSINESS = "business"
    SERVICE = "service"
    SERVICE_OFFER = "service_offer"
    LOCATION = "location"


SUPPORTED_SCOPES: frozenset[str] = frozenset(s.value for s in RuleScope)


# ---------------------------------------------------------------------------
# Action outcomes
# ---------------------------------------------------------------------------


class ActionOutcome(StrEnum):
    """Valid action outcomes for rules."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ESCALATE = "escalate"
    NOTIFY = "notify"
    ADJUST = "adjust"
    INFO = "info"


SUPPORTED_OUTCOMES: frozenset[str] = frozenset(o.value for o in ActionOutcome)


# ---------------------------------------------------------------------------
# Rule type definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleTypeDefinition:
    """Metadata for a registered rule type."""

    type_id: str
    category: ConfigCategory
    description: str
    schema_version: str = CURRENT_SCHEMA_VERSION
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    supported_operators: frozenset[str] = field(default_factory=lambda: SUPPORTED_OPERATORS)
    supported_scopes: frozenset[str] = field(
        default_factory=lambda: frozenset(s.value for s in RuleScope)
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class _RuleTypeRegistry:
    """Internal registry storage.  Populated at module load time."""

    def __init__(self) -> None:
        self._types: dict[str, RuleTypeDefinition] = {}

    def register(self, definition: RuleTypeDefinition) -> None:
        if definition.type_id in self._types:
            raise ValueError(f"Rule type '{definition.type_id}' is already registered")
        self._types[definition.type_id] = definition

    def get(self, type_id: str) -> RuleTypeDefinition | None:
        return self._types.get(type_id)

    def contains(self, type_id: str) -> bool:
        return type_id in self._types

    def all_types(self) -> dict[str, RuleTypeDefinition]:
        return dict(self._types)

    def types_for_category(self, category: ConfigCategory) -> list[RuleTypeDefinition]:
        return [d for d in self._types.values() if d.category == category]

    @property
    def count(self) -> int:
        return len(self._types)


# Module-level singleton
registry = _RuleTypeRegistry()


# ---------------------------------------------------------------------------
# Register all supported rule types
# ---------------------------------------------------------------------------

# A. Service Configuration
registry.register(
    RuleTypeDefinition(
        type_id="service_definition",
        category=ConfigCategory.SERVICE,
        description="Defines what a service includes/excludes",
        required_fields=("service_name",),
        optional_fields=("description", "includes", "excludes", "delivery_modes"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="service_bundling",
        category=ConfigCategory.SERVICE,
        description="Defines which services can be bundled",
        required_fields=("bundle_name", "service_ids"),
        optional_fields=("discount_percent", "min_services"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="service_exclusion",
        category=ConfigCategory.SERVICE,
        description="Defines what a service explicitly does not cover",
        required_fields=("exclusion_description",),
        optional_fields=("applies_to",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="service_customization",
        category=ConfigCategory.SERVICE,
        description="Defines allowed customizations per service",
        required_fields=("customization_name",),
        optional_fields=("options", "price_impact"),
    )
)

# B. Pricing Configuration
registry.register(
    RuleTypeDefinition(
        type_id="base_pricing",
        category=ConfigCategory.PRICING,
        description="Sets the base price for a service/offer",
        required_fields=("amount", "currency"),
        optional_fields=("pricing_model", "tax_inclusive"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="surcharge",
        category=ConfigCategory.PRICING,
        description="Adds conditional charges (weekend, holiday, urgency)",
        required_fields=("surcharge_name", "amount"),
        optional_fields=("conditions", "percentage"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="discount",
        category=ConfigCategory.PRICING,
        description="Provides conditional reductions (volume, loyalty, seasonal)",
        required_fields=("discount_name",),
        optional_fields=("percentage", "amount", "conditions", "max_discount"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="price_floor",
        category=ConfigCategory.PRICING,
        description="Sets minimum price boundaries",
        required_fields=("minimum_amount",),
        optional_fields=("currency",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="price_cap",
        category=ConfigCategory.PRICING,
        description="Sets maximum price boundaries",
        required_fields=("maximum_amount",),
        optional_fields=("currency",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="quote_threshold",
        category=ConfigCategory.PRICING,
        description="Defines when a custom quote is required vs. auto-pricing",
        required_fields=("threshold_type",),
        optional_fields=("threshold_value",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="payment_terms",
        category=ConfigCategory.PRICING,
        description="Defines payment timing requirements",
        required_fields=("payment_timing",),
        optional_fields=("late_fee_percent", "grace_period_days"),
    )
)

# C. Availability Configuration
registry.register(
    RuleTypeDefinition(
        type_id="operating_hours",
        category=ConfigCategory.AVAILABILITY,
        description="Defines when business is available",
        required_fields=("day_of_week", "open_time", "close_time"),
        optional_fields=("timezone", "break_start", "break_end"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="minimum_notice",
        category=ConfigCategory.AVAILABILITY,
        description="Sets minimum advance notice requirements",
        required_fields=("notice_hours",),
        optional_fields=("applies_to",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="maximum_advance",
        category=ConfigCategory.AVAILABILITY,
        description="Sets maximum forward booking window",
        required_fields=("advance_days",),
        optional_fields=("applies_to",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="capacity_limit",
        category=ConfigCategory.AVAILABILITY,
        description="Defines capacity constraints",
        required_fields=("max_capacity",),
        optional_fields=("time_window_minutes", "applies_to"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="blackout_period",
        category=ConfigCategory.AVAILABILITY,
        description="Defines when service is unavailable",
        required_fields=("start_date", "end_date"),
        optional_fields=("reason", "recurring"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="slot_configuration",
        category=ConfigCategory.AVAILABILITY,
        description="Defines time slot structure",
        required_fields=("slot_duration_minutes",),
        optional_fields=("buffer_minutes", "max_slots_per_window"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="concurrent_limit",
        category=ConfigCategory.AVAILABILITY,
        description="Limits simultaneous services",
        required_fields=("max_concurrent",),
        optional_fields=("applies_to",),
    )
)

# D. Qualification Configuration
registry.register(
    RuleTypeDefinition(
        type_id="required_information",
        category=ConfigCategory.QUALIFICATION,
        description="Defines mandatory customer-provided data",
        required_fields=("field_name",),
        optional_fields=("field_type", "prompt_text"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="conditional_information",
        category=ConfigCategory.QUALIFICATION,
        description="Defines data required under specific conditions",
        required_fields=("field_name", "condition"),
        optional_fields=("field_type", "prompt_text"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="document_requirement",
        category=ConfigCategory.QUALIFICATION,
        description="Defines documents that must be uploaded",
        required_fields=("document_type",),
        optional_fields=("mandatory", "description"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="verification_requirement",
        category=ConfigCategory.QUALIFICATION,
        description="Defines what must be verified before proceeding",
        required_fields=("verification_type",),
        optional_fields=("method", "timeout_hours"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="eligibility_check",
        category=ConfigCategory.QUALIFICATION,
        description="Defines customer eligibility criteria",
        required_fields=("criteria_type",),
        optional_fields=("criteria_value", "error_message"),
    )
)

# E. Policy Configuration (includes booking, cancellation, rescheduling)
registry.register(
    RuleTypeDefinition(
        type_id="cancellation_policy",
        category=ConfigCategory.POLICY,
        description="Defines cancellation windows, fees, conditions",
        required_fields=("window_hours",),
        optional_fields=("fee_percent", "fee_amount", "reasons"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="refund_policy",
        category=ConfigCategory.POLICY,
        description="Defines refund eligibility and amounts",
        required_fields=("refund_type",),
        optional_fields=("refund_percent", "conditions"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="modification_policy",
        category=ConfigCategory.POLICY,
        description="Defines what can be changed and when",
        required_fields=("modifiable_fields",),
        optional_fields=("window_hours", "approval_required"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="terms_of_service",
        category=ConfigCategory.POLICY,
        description="Defines general service terms",
        required_fields=("terms_text",),
        optional_fields=("version", "effective_date"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="liability_policy",
        category=ConfigCategory.POLICY,
        description="Defines liability limitations",
        required_fields=("limitation_type",),
        optional_fields=("max_liability", "exclusions"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="guarantee_policy",
        category=ConfigCategory.POLICY,
        description="Defines service guarantees",
        required_fields=("guarantee_type",),
        optional_fields=("duration_hours", "remedy"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="complaint_policy",
        category=ConfigCategory.POLICY,
        description="Defines complaint handling procedures",
        required_fields=("response_window_hours",),
        optional_fields=("escalation_steps",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="booking_creation",
        category=ConfigCategory.POLICY,
        description="Defines how bookings can be initiated",
        required_fields=("initiation_method",),
        optional_fields=("requires_confirmation", "auto_confirm"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="confirmation_rules",
        category=ConfigCategory.POLICY,
        description="Defines confirmation requirements",
        required_fields=("confirmation_method",),
        optional_fields=("timeout_minutes", "auto_confirm_after"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="deposit_rules",
        category=ConfigCategory.POLICY,
        description="Defines deposit requirements",
        required_fields=("deposit_required",),
        optional_fields=("deposit_percent", "deposit_amount", "due_before_hours"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="reminder_schedule",
        category=ConfigCategory.POLICY,
        description="Defines pre-service reminder timing",
        required_fields=("reminders",),
        optional_fields=("channel",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="auto_confirmation",
        category=ConfigCategory.POLICY,
        description="Defines conditions for automatic confirmation",
        required_fields=("enabled",),
        optional_fields=("conditions", "timeout_minutes"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="cancellation_window",
        category=ConfigCategory.POLICY,
        description="Time-based cancellation eligibility",
        required_fields=("hours_before_service",),
        optional_fields=("allowed",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="cancellation_fee",
        category=ConfigCategory.POLICY,
        description="Fee calculation rules",
        required_fields=("fee_type",),
        optional_fields=("amount", "percent", "window_hours"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="cancellation_reason",
        category=ConfigCategory.POLICY,
        description="Which reasons are accepted",
        required_fields=("accepted_reasons",),
        optional_fields=("requires_evidence",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="auto_cancellation",
        category=ConfigCategory.POLICY,
        description="Automatic cancellation conditions",
        required_fields=("trigger_condition",),
        optional_fields=("grace_period_minutes",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="cancellation_approval",
        category=ConfigCategory.POLICY,
        description="When cancellation requires approval",
        required_fields=("approval_required",),
        optional_fields=("approver_role", "timeout_hours"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="reschedule_window",
        category=ConfigCategory.POLICY,
        description="When rescheduling is allowed",
        required_fields=("hours_before_service",),
        optional_fields=("allowed",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="reschedule_limit",
        category=ConfigCategory.POLICY,
        description="How many times a booking can be rescheduled",
        required_fields=("max_reschedules",),
        optional_fields=("per_customer", "per_booking"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="reschedule_fee",
        category=ConfigCategory.POLICY,
        description="Fee calculation for rescheduling",
        required_fields=("fee_type",),
        optional_fields=("amount", "percent", "window_hours"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="reschedule_availability",
        category=ConfigCategory.POLICY,
        description="Whether new time must satisfy availability",
        required_fields=("check_availability",),
        optional_fields=("strict",),
    )
)

# I. Communication Configuration
registry.register(
    RuleTypeDefinition(
        type_id="response_time",
        category=ConfigCategory.COMMUNICATION,
        description="Target response time per context",
        required_fields=("target_hours",),
        optional_fields=("context", "max_hours"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="channel_preference",
        category=ConfigCategory.COMMUNICATION,
        description="Preferred communication channel per context",
        required_fields=("channel",),
        optional_fields=("priority", "context"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="tone_policy",
        category=ConfigCategory.COMMUNICATION,
        description="Communication tone requirements",
        required_fields=("tone",),
        optional_fields=("context",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="template_selection",
        category=ConfigCategory.COMMUNICATION,
        description="Which templates to use for which messages",
        required_fields=("template_id", "trigger"),
        optional_fields=("variables",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="auto_response",
        category=ConfigCategory.COMMUNICATION,
        description="Automated response rules",
        required_fields=("trigger", "response_template"),
        optional_fields=("conditions",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="escalation_notification",
        category=ConfigCategory.COMMUNICATION,
        description="When to notify business members",
        required_fields=("notification_trigger",),
        optional_fields=("recipients", "channel"),
    )
)

# J. Escalation Configuration
registry.register(
    RuleTypeDefinition(
        type_id="value_threshold",
        category=ConfigCategory.ESCALATION,
        description="Escalate when value exceeds threshold",
        required_fields=("threshold_amount",),
        optional_fields=("currency", "approver_role"),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="complexity_trigger",
        category=ConfigCategory.ESCALATION,
        description="Escalate based on complexity indicators",
        required_fields=("indicator",),
        optional_fields=("threshold",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="customer_request",
        category=ConfigCategory.ESCALATION,
        description="Escalate when customer explicitly requests human",
        required_fields=("enabled",),
        optional_fields=("keywords",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="conflict_escalation",
        category=ConfigCategory.ESCALATION,
        description="Escalate on rule conflicts",
        required_fields=("enabled",),
        optional_fields=("resolution_strategy",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="timeout_escalation",
        category=ConfigCategory.ESCALATION,
        description="Escalate when response time exceeded",
        required_fields=("timeout_minutes",),
        optional_fields=("escalation_target",),
    )
)
registry.register(
    RuleTypeDefinition(
        type_id="repeat_escalation",
        category=ConfigCategory.ESCALATION,
        description="Escalate after N failed automated attempts",
        required_fields=("max_attempts",),
        optional_fields=("cooldown_minutes",),
    )
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_rule_type(type_id: str) -> RuleTypeDefinition | None:
    """Look up a rule type definition.  Returns None if unknown."""
    return registry.get(type_id)


def is_known_rule_type(type_id: str) -> bool:
    """Check whether a rule type is registered."""
    return registry.contains(type_id)


def get_all_rule_types() -> dict[str, RuleTypeDefinition]:
    """Return all registered rule type definitions."""
    return registry.all_types()


def get_rule_types_for_category(category: ConfigCategory) -> list[RuleTypeDefinition]:
    """Return all rule types belonging to a configuration category."""
    return registry.types_for_category(category)


def is_supported_operator(operator: str) -> bool:
    """Check whether a condition operator is supported."""
    return operator in SUPPORTED_OPERATORS


def is_supported_scope(scope: str) -> bool:
    """Check whether a rule scope is supported."""
    return scope in SUPPORTED_SCOPES


def is_supported_outcome(outcome: str) -> bool:
    """Check whether an action outcome is supported."""
    return outcome in SUPPORTED_OUTCOMES


def is_supported_schema_version(version: str) -> bool:
    """Check whether a schema version is supported."""
    return version in SUPPORTED_SCHEMA_VERSIONS
