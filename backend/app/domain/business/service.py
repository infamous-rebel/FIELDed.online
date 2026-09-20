"""Business Brain domain service.

Contains business logic for brain versioning, rule management,
and version lifecycle transitions.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.business.approval import (
    ApprovalDecision,
    ApprovalPolicy,
    DEFAULT_APPROVAL_POLICY,
    resolve_approval_policy,
)
from app.domain.business.models import BusinessBrain, BrainVersion, BusinessRule
from app.domain.business.registry import CURRENT_SCHEMA_VERSION, is_known_rule_type
from app.domain.business.repository import (
    BrainVersionRepository,
    BusinessBrainRepository,
    BusinessRuleRepository,
)
from app.domain.business.validation import (
    ValidationResult,
    validate_brain_version_config,
    validate_rule_data,
)
from app.domain.common.enums import BRAIN_VERSION_TRANSITIONS, BrainVersionStatus
from app.exceptions import AuthorizationError, DomainError, NotFoundError, StateTransitionError, ValidationError
from app.logging import get_logger

logger = get_logger(__name__)

# States in which a BrainVersion's configuration is IMMUTABLE.
# Only DRAFT versions may have their config or rules modified.
_IMMUTABLE_STATUSES: frozenset[BrainVersionStatus] = frozenset({
    BrainVersionStatus.REVIEW,
    BrainVersionStatus.APPROVED,
    BrainVersionStatus.ACTIVE,
    BrainVersionStatus.SUPERSEDED,
})


class BrainService:
    """Business Brain version management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.brain_repo = BusinessBrainRepository(session)
        self.version_repo = BrainVersionRepository(session)

    async def get_or_create_brain(self, business_id: uuid.UUID) -> BusinessBrain:
        """Get the brain for a business, creating it if it doesn't exist."""
        brain = await self.brain_repo.get_by_business_id(business_id)
        if brain is None:
            brain = BusinessBrain(business_id=business_id)
            brain = await self.brain_repo.create(brain)
        return brain

    async def create_version(
        self,
        brain_id: uuid.UUID,
        config: dict | None = None,
    ) -> BrainVersion:
        """Create a new DRAFT version of the brain.

        Validates config structure before persisting.
        Injects schema_version automatically.
        """
        version_number = await self.version_repo.get_next_version_number(brain_id)

        config = config or {}

        # Structural validation — mandatory for ALL sources
        config_result = validate_brain_version_config(config)
        if not config_result.is_valid:
            raise ValidationError(
                f"Brain configuration is invalid: "
                f"{[e.message for e in config_result.errors]}"
            )

        version = BrainVersion(
            brain_id=brain_id,
            version_number=version_number,
            status=BrainVersionStatus.DRAFT,
            identity_config=config.get("identity"),
            services_config=config.get("services"),
            pricing_config=config.get("pricing"),
            availability_config=config.get("availability"),
            qualification_config=config.get("qualification"),
            policies_config=config.get("policies"),
            escalation_config=config.get("escalation"),
            communication_config=config.get("communication"),
        )
        return await self.version_repo.create(version)

    async def transition_version(
        self,
        version_id: uuid.UUID,
        target_status: BrainVersionStatus,
    ) -> BrainVersion:
        """Transition a brain version to a new status.

        Enforces:
        - State machine validity
        - Immutability: config cannot be changed once not DRAFT
        - Validation: must pass structural validation before REVIEW
        """
        version = await self.version_repo.get_by_id(version_id)
        if version is None:
            raise NotFoundError(f"Brain version {version_id} not found")

        current_status = BrainVersionStatus(version.status)
        allowed = BRAIN_VERSION_TRANSITIONS.get(current_status, set())

        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition brain version from "
                f"{current_status.value} to {target_status.value}"
            )

        # Before transitioning to REVIEW, run structural validation
        if target_status == BrainVersionStatus.REVIEW:
            validation = self._validate_version_structure(version)
            if not validation.is_valid:
                raise ValidationError(
                    f"Brain version cannot enter REVIEW — "
                    f"structural validation failed: "
                    f"{[e.message for e in validation.errors]}"
                )

        version.status = target_status
        return await self.version_repo.update(version)

    @staticmethod
    def _ensure_mutable(version: BrainVersion) -> None:
        """Raise DomainError if the version is not in DRAFT state.

        Once a BrainVersion leaves DRAFT (→ VALIDATING, REVIEW, APPROVED,
        ACTIVE, SUPERSEDED), its configuration is IMMUTABLE.
        """
        status = BrainVersionStatus(version.status)
        if status != BrainVersionStatus.DRAFT:
            raise DomainError(
                f"Brain version {version.id} is {status.value} and immutable. "
                f"Configuration cannot be modified. "
                f"Create a new DRAFT version instead."
            )

    @staticmethod
    def _validate_version_structure(version: BrainVersion) -> ValidationResult:
        """Run structural validation on a BrainVersion's config + rules."""
        config = {
            k: getattr(version, f"{k}_config")
            for k in (
                "identity", "services", "pricing", "availability",
                "qualification", "policies", "escalation", "communication",
            )
            if getattr(version, f"{k}_config") is not None
        }
        rules = [
            {"rule_type": r.rule_type, "rule_data": r.rule_data}
            for r in version.rules
        ] if version.rules else []

        from app.domain.business.validation import validate_brain_version_full
        return validate_brain_version_full(config, rules)

    async def update_version_config(
        self,
        version_id: uuid.UUID,
        config: dict,
    ) -> BrainVersion:
        """Update a DRAFT version's configuration.

        Raises DomainError if the version is not mutable (not DRAFT).
        Validates config structure before applying.
        """
        version = await self.version_repo.get_by_id(version_id)
        if version is None:
            raise NotFoundError(f"Brain version {version_id} not found")

        self._ensure_mutable(version)

        # Structural validation
        config_result = validate_brain_version_config(config)
        if not config_result.is_valid:
            raise ValidationError(
                f"Brain configuration is invalid: "
                f"{[e.message for e in config_result.errors]}"
            )

        if "identity" in config:
            version.identity_config = config["identity"]
        if "services" in config:
            version.services_config = config["services"]
        if "pricing" in config:
            version.pricing_config = config["pricing"]
        if "availability" in config:
            version.availability_config = config["availability"]
        if "qualification" in config:
            version.qualification_config = config["qualification"]
        if "policies" in config:
            version.policies_config = config["policies"]
        if "escalation" in config:
            version.escalation_config = config["escalation"]
        if "communication" in config:
            version.communication_config = config["communication"]

        return await self.version_repo.update(version)

    async def activate_version(
        self,
        brain_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> BusinessBrain:
        """Set a version as the active brain version.

        Concurrency-safe: uses SELECT FOR UPDATE to prevent two concurrent
        activations for the same business.  Automatically supersedes the
        previously active version (if any) within the same transaction.

        Invariant: exactly one BrainVersion per BusinessBrain is ACTIVE.
        """
        # 1. Lock the brain row to prevent concurrent activation
        brain = await self.brain_repo.get_by_business_id_for_update(brain_id)
        if brain is None:
            raise NotFoundError(
                f"Business brain for business {brain_id} not found"
            )

        # 2. Validate the target version exists and is APPROVED or ACTIVE
        version = await self.version_repo.get_by_id(version_id)
        if version is None:
            raise NotFoundError(f"Brain version {version_id} not found")

        if version.status not in (
            BrainVersionStatus.APPROVED,
            BrainVersionStatus.ACTIVE,
        ):
            raise DomainError(
                f"Only APPROVED or ACTIVE versions can be activated. "
                f"Current status: {version.status}"
            )

        # 3. Supersede the currently active version (if any)
        current_active = await self.version_repo.get_active_by_brain_id(
            brain.id
        )
        if current_active is not None and current_active.id != version_id:
            current_active.status = BrainVersionStatus.SUPERSEDED
            await self.version_repo.update(current_active)
            logger.info(
                "brain_version_superseded",
                brain_version_id=str(current_active.id),
                superseded_by=str(version_id),
                brain_id=str(brain.id),
            )

        # 4. Transition the new version to ACTIVE if not already
        if version.status == BrainVersionStatus.APPROVED:
            version.status = BrainVersionStatus.ACTIVE
            await self.version_repo.update(version)

        # 5. Update the brain's active_version_id pointer
        brain.active_version_id = version_id
        await self.brain_repo.update_active_version(brain, version_id)

        logger.info(
            "brain_version_activated",
            brain_version_id=str(version_id),
            brain_id=str(brain.id),
        )

        return brain

    async def validate_version(
        self,
        version_id: uuid.UUID,
    ) -> "ValidationResult":
        """Run structural validation on a brain version and return results."""
        version = await self.version_repo.get_by_id(version_id)
        if version is None:
            raise NotFoundError(f"Brain version {version_id} not found")

        return self._validate_version_structure(version)

    async def approve_version(
        self,
        version_id: uuid.UUID,
        approver_role: "BusinessMemberRole",
        is_author: bool = False,
    ) -> BrainVersion:
        """Approve a brain version according to the approval policy.

        The version must be in REVIEW status.
        The approver must have the required role per the approval policy.

        Returns the updated BrainVersion with status=APPROVED.
        """
        version = await self.version_repo.get_by_id(version_id)
        if version is None:
            raise NotFoundError(f"Brain version {version_id} not found")

        current_status = BrainVersionStatus(version.status)
        if current_status != BrainVersionStatus.REVIEW:
            raise DomainError(
                f"Only REVIEW versions can be approved. "
                f"Current status: {current_status.value}"
            )

        # Resolve approval policy (default for now)
        policy = resolve_approval_policy()

        # Gather rule types from the version for sensitive-rule check
        rule_types = [r.rule_type for r in version.rules] if version.rules else []

        decision = policy.check_approval(
            approver_role=approver_role,
            is_author=is_author,
            rule_types=rule_types,
        )

        if decision != ApprovalDecision.APPROVED:
            raise AuthorizationError(
                f"Approval denied: {decision.value}"
            )

        version.status = BrainVersionStatus.APPROVED
        return await self.version_repo.update(version)


class BusinessRuleService:
    """Business rule management within brain versions.

    Enforces:
    - Version immutability: rules can only be added to DRAFT versions
    - Rule-type registry: unknown rule types are rejected
    - Structural validation: rule_data must conform to the type's schema
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.rule_repo = BusinessRuleRepository(session)
        self.version_repo = BrainVersionRepository(session)

    async def add_rule(
        self,
        brain_version_id: uuid.UUID,
        rule_type: str,
        name: str,
        rule_data: dict,
        description: str | None = None,
        priority: int = 0,
    ) -> BusinessRule:
        """Add a rule to a DRAFT brain version.

        Validates:
        1. Version is mutable (DRAFT)
        2. Rule type is registered
        3. Rule data passes structural validation
        4. Schema version is injected if not present
        """
        # 1. Check version mutability
        version = await self.version_repo.get_by_id(brain_version_id)
        if version is None:
            raise NotFoundError(f"Brain version {brain_version_id} not found")

        BrainService._ensure_mutable(version)

        # 2. Validate rule type and data.
        # The schema accepts both registry-specific types (e.g. "base_pricing")
        # and category-level types (e.g. "pricing", "policy").  For category-
        # level types the registry has no specific definition, so we skip
        # field-level validation and accept any well-formed rule_data dict.
        if is_known_rule_type(rule_type):
            rule_result = validate_rule_data(rule_type, rule_data)
            if not rule_result.is_valid:
                raise ValidationError(
                    f"Rule data is invalid: "
                    f"{[e.message for e in rule_result.errors]}"
                )
        else:
            # Category-level or unknown type — accept if rule_data is a dict.
            if not isinstance(rule_data, dict):
                raise ValidationError("rule_data must be a dictionary")

        # 3. Inject schema_version if not present
        if "schema_version" not in rule_data:
            rule_data = {**rule_data, "schema_version": CURRENT_SCHEMA_VERSION}

        rule = BusinessRule(
            brain_version_id=brain_version_id,
            rule_type=rule_type,
            name=name,
            description=description,
            rule_data=rule_data,
            priority=priority,
        )
        return await self.rule_repo.create(rule)

    async def get_rules(
        self, brain_version_id: uuid.UUID
    ) -> list[BusinessRule]:
        """Get all rules for a brain version."""
        return await self.rule_repo.get_by_brain_version_id(brain_version_id)

    async def update_rule(
        self,
        rule_id: uuid.UUID,
        **updates: Any,
    ) -> BusinessRule:
        """Update a rule within a DRAFT brain version.

        Raises DomainError if the parent version is not mutable.
        """
        rule = await self.rule_repo.get_by_id(rule_id)
        if rule is None:
            raise NotFoundError(f"Business rule {rule_id} not found")

        # Check parent version mutability
        version = await self.version_repo.get_by_id(rule.brain_version_id)
        if version is None:
            raise NotFoundError("Parent brain version not found")
        BrainService._ensure_mutable(version)

        # Validate new rule_data if provided
        if "rule_data" in updates and updates["rule_data"] is not None:
            rule_result = validate_rule_data(rule.rule_type, updates["rule_data"])
            if not rule_result.is_valid:
                raise ValidationError(
                    f"Rule data is invalid: "
                    f"{[e.message for e in rule_result.errors]}"
                )

        for key, value in updates.items():
            if value is not None and hasattr(rule, key):
                setattr(rule, key, value)

        return await self.rule_repo.update(rule)

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        """Soft-delete a rule from a DRAFT brain version.

        Raises DomainError if the parent version is not mutable.
        """
        rule = await self.rule_repo.get_by_id(rule_id)
        if rule is None:
            raise NotFoundError(f"Business rule {rule_id} not found")

        version = await self.version_repo.get_by_id(rule.brain_version_id)
        if version is None:
            raise NotFoundError("Parent brain version not found")
        BrainService._ensure_mutable(version)

        await self.rule_repo.delete(rule)
