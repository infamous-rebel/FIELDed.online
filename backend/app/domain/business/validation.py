"""Business Brain structural validation.

Every Brain configuration must pass structural validation before entering
REVIEW or becoming APPROVED/ACTIVE.  This applies regardless of provenance
(human, AI, import, template, system, integration).

Structural validation is SEPARATE from deterministic runtime evaluation.
The evaluator is NOT responsible for configuration validation.

Validation errors are returned as structured data suitable for future
API responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.business.registry import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_OPERATORS,
    SUPPORTED_SCHEMA_VERSIONS,
    SUPPORTED_SCOPES,
    ConfigCategory,
    get_rule_type,
    is_known_rule_type,
    is_supported_operator,
    is_supported_schema_version,
    is_supported_scope,
)

# ---------------------------------------------------------------------------
# Validation error structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationErrorDetail:
    """A single validation error."""

    field: str
    message: str
    code: str  # Machine-readable error code


@dataclass
class ValidationResult:
    """Result of structural validation.

    Use `is_valid` to check pass/fail.
    Use `errors` to inspect individual issues.
    """

    errors: list[ValidationErrorDetail] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field_name: str, message: str, code: str = "invalid") -> None:
        self.errors.append(
            ValidationErrorDetail(
                field=field_name,
                message=message,
                code=code,
            )
        )

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "valid": self.is_valid,
            "error_count": len(self.errors),
            "errors": [{"field": e.field, "message": e.message, "code": e.code} for e in self.errors],
        }


# ---------------------------------------------------------------------------
# Configuration area → ConfigCategory mapping
# ---------------------------------------------------------------------------

CONFIG_AREA_FIELDS: dict[str, ConfigCategory] = {
    "identity": ConfigCategory.SERVICE,  # identity maps to service for now
    "services": ConfigCategory.SERVICE,
    "pricing": ConfigCategory.PRICING,
    "availability": ConfigCategory.AVAILABILITY,
    "qualification": ConfigCategory.QUALIFICATION,
    "policies": ConfigCategory.POLICY,
    "escalation": ConfigCategory.ESCALATION,
    "communication": ConfigCategory.COMMUNICATION,
}

SUPPORTED_CONFIG_AREAS: frozenset[str] = frozenset(CONFIG_AREA_FIELDS.keys())


# ---------------------------------------------------------------------------
# BrainVersion config validation
# ---------------------------------------------------------------------------


def validate_brain_version_config(
    config: dict[str, Any] | None,
) -> ValidationResult:
    """Validate a BrainVersion configuration dictionary.

    Checks:
    - config is a dict (or None)
    - no unknown configuration areas
    - each area's value is a dict (or None)
    - schema_version is present and supported (if provided at top level)

    This validates the STRUCTURE of the config envelope, not the content
    of individual rules (which are validated separately).
    """
    result = ValidationResult()

    if config is None:
        return result  # Empty config is valid

    if not isinstance(config, dict):
        result.add_error("config", "Configuration must be a dictionary", "type_error")
        return result

    # Check for unknown configuration areas
    for key in config:
        if key not in SUPPORTED_CONFIG_AREAS and key != "schema_version":
            result.add_error(
                f"config.{key}",
                f"Unknown configuration area: '{key}'. Supported areas: {sorted(SUPPORTED_CONFIG_AREAS)}",
                "unknown_config_area",
            )

    # Check each area's value type
    for area_name in SUPPORTED_CONFIG_AREAS:
        if area_name in config and config[area_name] is not None and not isinstance(config[area_name], dict):
            result.add_error(
                f"config.{area_name}",
                f"Configuration area '{area_name}' must be a dictionary or null",
                "type_error",
            )

    # Check schema_version if present
    if "schema_version" in config:
        sv = config["schema_version"]
        if not isinstance(sv, str):
            result.add_error(
                "config.schema_version",
                "schema_version must be a string",
                "type_error",
            )
        elif not is_supported_schema_version(sv):
            result.add_error(
                "config.schema_version",
                f"Unsupported schema version: '{sv}'. Supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
                "unsupported_schema_version",
            )

    return result


# ---------------------------------------------------------------------------
# BusinessRule validation
# ---------------------------------------------------------------------------


def validate_rule_data(
    rule_type: str,
    rule_data: dict[str, Any],
    *,
    schema_version: str | None = None,
) -> ValidationResult:
    """Validate a BusinessRule's type and data structure.

    Checks:
    - rule_type is a known registered type
    - rule_data is a dict
    - schema_version is supported (if provided)
    - required fields for the rule type are present
    - no unknown fields (warns but does not reject extra fields at this stage)
    - condition structure is valid (if conditions present)
    - action structure is valid (if actions present)
    - scope is valid (if scope present)
    - priority is a non-negative integer (if priority present)
    """
    result = ValidationResult()

    # 1. Rule type must be known
    if not is_known_rule_type(rule_type):
        result.add_error(
            "rule_type",
            f"Unknown rule type: '{rule_type}'. Use the rule-type registry to determine supported types.",
            "unknown_rule_type",
        )
        # Cannot validate further without knowing the type
        return result

    definition = get_rule_type(rule_type)
    assert definition is not None  # guaranteed by is_known_rule_type

    # 2. rule_data must be a dict
    if not isinstance(rule_data, dict):
        result.add_error(
            "rule_data",
            "rule_data must be a dictionary",
            "type_error",
        )
        return result

    # 3. Schema version check
    effective_version = schema_version or rule_data.get("schema_version") or CURRENT_SCHEMA_VERSION
    if not is_supported_schema_version(effective_version):
        result.add_error(
            "rule_data.schema_version",
            f"Unsupported schema version: '{effective_version}'. Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
            "unsupported_schema_version",
        )

    # 4. Required fields
    for required_field in definition.required_fields:
        if required_field not in rule_data:
            result.add_error(
                f"rule_data.{required_field}",
                f"Required field '{required_field}' is missing for rule type '{rule_type}'",
                "missing_required_field",
            )

    # 5. Validate conditions structure (if present)
    if "conditions" in rule_data:
        _validate_conditions(rule_data["conditions"], result)

    # 6. Validate actions structure (if present)
    if "actions" in rule_data:
        _validate_actions(rule_data["actions"], result)

    # 7. Validate scope (if present)
    if "scope" in rule_data:
        scope = rule_data["scope"]
        if not isinstance(scope, str) or not is_supported_scope(scope):
            result.add_error(
                "rule_data.scope",
                f"Invalid scope: '{scope}'. Supported: {sorted(SUPPORTED_SCOPES)}",
                "invalid_scope",
            )

    # 8. Validate priority (if present)
    if "priority" in rule_data:
        priority = rule_data["priority"]
        if not isinstance(priority, int) or priority < 0:
            result.add_error(
                "rule_data.priority",
                "Priority must be a non-negative integer",
                "invalid_priority",
            )

    # 9. Validate effective dates (if present)
    if "effective_from" in rule_data:
        _validate_date_string(rule_data["effective_from"], "rule_data.effective_from", result)
    if "effective_until" in rule_data:
        _validate_date_string(rule_data["effective_until"], "rule_data.effective_until", result)

    return result


def _validate_conditions(
    conditions: Any,
    result: ValidationResult,
) -> None:
    """Validate the conditions structure of a rule."""
    if not isinstance(conditions, list):
        result.add_error(
            "rule_data.conditions",
            "Conditions must be a list",
            "type_error",
        )
        return

    for i, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            result.add_error(
                f"rule_data.conditions[{i}]",
                "Each condition must be a dictionary",
                "type_error",
            )
            continue

        # Each condition must have field, operator, value
        if "field" not in condition:
            result.add_error(
                f"rule_data.conditions[{i}].field",
                "Condition must have a 'field' property",
                "missing_required_field",
            )
        if "operator" not in condition:
            result.add_error(
                f"rule_data.conditions[{i}].operator",
                "Condition must have an 'operator' property",
                "missing_required_field",
            )
        else:
            op = condition["operator"]
            if not isinstance(op, str) or not is_supported_operator(op):
                result.add_error(
                    f"rule_data.conditions[{i}].operator",
                    f"Unknown operator: '{op}'. Supported: {sorted(SUPPORTED_OPERATORS)}",
                    "unknown_operator",
                )

        # value is required unless operator is is_empty/is_not_empty
        op = condition.get("operator", "")
        if op not in ("is_empty", "is_not_empty") and "value" not in condition:
            result.add_error(
                f"rule_data.conditions[{i}].value",
                f"Condition with operator '{op}' must have a 'value' property",
                "missing_required_field",
            )


def _validate_actions(
    actions: Any,
    result: ValidationResult,
) -> None:
    """Validate the actions structure of a rule."""
    if not isinstance(actions, list):
        result.add_error(
            "rule_data.actions",
            "Actions must be a list",
            "type_error",
        )
        return

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            result.add_error(
                f"rule_data.actions[{i}]",
                "Each action must be a dictionary",
                "type_error",
            )
            continue

        if "outcome" not in action:
            result.add_error(
                f"rule_data.actions[{i}].outcome",
                "Action must have an 'outcome' property",
                "missing_required_field",
            )
        else:
            outcome = action["outcome"]
            from app.domain.business.registry import SUPPORTED_OUTCOMES

            if not isinstance(outcome, str) or outcome not in SUPPORTED_OUTCOMES:
                result.add_error(
                    f"rule_data.actions[{i}].outcome",
                    f"Unknown action outcome: '{outcome}'. Supported: {sorted(SUPPORTED_OUTCOMES)}",
                    "unknown_outcome",
                )


def _validate_date_string(
    value: Any,
    field_name: str,
    result: ValidationResult,
) -> None:
    """Validate that a value looks like an ISO date string."""
    if not isinstance(value, str):
        result.add_error(field_name, "Date must be an ISO 8601 string", "type_error")
        return
    # Basic format check — full datetime parsing is not required here
    if len(value) < 10 or value[4] != "-":
        result.add_error(
            field_name,
            f"Date must be ISO 8601 format, got: '{value}'",
            "invalid_date_format",
        )


# ---------------------------------------------------------------------------
# Full BrainVersion validation (config + rules)
# ---------------------------------------------------------------------------


def validate_brain_version_full(
    config: dict[str, Any] | None,
    rules: list[dict[str, Any]],
) -> ValidationResult:
    """Validate a complete BrainVersion: config envelope + all rules.

    This is the entry point called before transitioning to REVIEW.
    """
    result = validate_brain_version_config(config)

    if not isinstance(rules, list):
        result.add_error("rules", "Rules must be a list", "type_error")
        return result

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            result.add_error(f"rules[{i}]", "Each rule must be a dictionary", "type_error")
            continue

        rule_type = rule.get("rule_type", "")
        rule_data = rule.get("rule_data", {})
        schema_version = rule.get("schema_version")

        if not rule_type:
            result.add_error(
                f"rules[{i}].rule_type",
                "Rule must have a 'rule_type' property",
                "missing_required_field",
            )
            continue

        rule_result = validate_rule_data(rule_type, rule_data, schema_version=schema_version)
        # Prefix errors with rule index
        for err in rule_result.errors:
            result.add_error(f"rules[{i}].{err.field}", err.message, err.code)

    return result
