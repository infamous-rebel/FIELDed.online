"""Business Brain API endpoints.

Provides authenticated Brain management: version CRUD, rule management,
structural validation, lifecycle transitions, approval, and activation.

All endpoints enforce tenant isolation through the Phase 07 authorization
dependencies.  No cross-tenant access is possible.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.business.auth import (
    require_brain_access,
    require_brain_approve,
    require_brain_modify,
    require_brain_version_access,
    require_brain_version_modify,
)
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.business.schemas import (
    ApprovalRequest,
    ApprovalResultRead,
    BrainVersionCreate,
    BrainVersionRead,
    BrainVersionSummaryRead,
    BrainVersionTransitionRead,
    BrainVersionTransitionRequest,
    BrainVersionUpdate,
    BusinessBrainDetailRead,
    BusinessBrainRead,
    BusinessRuleCreate,
    BusinessRuleRead,
    BusinessRuleUpdate,
    ProvenanceEntryRead,
    ProvenanceRead,
    ValidationErrorDetail,
    ValidationResultRead,
)
from app.domain.business.service import BrainService, BusinessRuleService
from app.domain.common.enums import BrainVersionStatus, BusinessMemberRole
from app.domain.identity.models import User
from app.exceptions import NotFoundError
from app.security.authorization import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _version_to_read(version: BrainVersion) -> BrainVersionRead:
    """Convert a BrainVersion model to the detail read schema."""
    rules = [BusinessRuleRead.model_validate(r) for r in (version.rules or [])]
    return BrainVersionRead(
        id=version.id,
        brain_id=version.brain_id,
        version_number=version.version_number,
        status=version.status,
        identity_config=version.identity_config,
        services_config=version.services_config,
        pricing_config=version.pricing_config,
        availability_config=version.availability_config,
        qualification_config=version.qualification_config,
        policies_config=version.policies_config,
        escalation_config=version.escalation_config,
        communication_config=version.communication_config,
        rules=rules,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


def _version_to_summary(version: BrainVersion) -> BrainVersionSummaryRead:
    """Convert a BrainVersion to the lightweight summary schema."""
    return BrainVersionSummaryRead(
        id=version.id,
        brain_id=version.brain_id,
        version_number=version.version_number,
        status=version.status,
        identity_config=version.identity_config,
        services_config=version.services_config,
        pricing_config=version.pricing_config,
        availability_config=version.availability_config,
        qualification_config=version.qualification_config,
        policies_config=version.policies_config,
        escalation_config=version.escalation_config,
        communication_config=version.communication_config,
        rule_count=len(version.rules) if version.rules else 0,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /brain — Retrieve brain summary + active version
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/brain",
    response_model=BusinessBrainDetailRead,
)
async def get_brain(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessBrainDetailRead:
    """Return the Business Brain summary and currently ACTIVE version.

    Any authorized business member (staff+) can read.
    """
    # Find the active version if set
    active_version = None
    if brain.active_version_id:
        from app.domain.business.repository import BrainVersionRepository

        version_repo = BrainVersionRepository(db)
        active_version = await version_repo.get_by_id(brain.active_version_id)

    # Count versions via explicit query (async doesn't support lazy loading)
    from sqlalchemy import func, select

    from app.domain.business.models import BrainVersion

    result = await db.execute(select(func.count()).select_from(BrainVersion).where(BrainVersion.brain_id == brain.id))
    version_count = result.scalar() or 0

    return BusinessBrainDetailRead(
        id=brain.id,
        business_id=brain.business_id,
        active_version_id=brain.active_version_id,
        active_version=_version_to_read(active_version) if active_version else None,
        version_count=version_count,
        created_at=brain.created_at,
        updated_at=brain.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /brain/versions — List all versions
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/brain/versions",
    response_model=list[BrainVersionSummaryRead],
)
async def list_versions(
    brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[BrainVersionSummaryRead]:
    """List all BrainVersions for this business, newest first."""
    from app.domain.business.repository import BrainVersionRepository

    version_repo = BrainVersionRepository(db)
    versions = await version_repo.get_by_brain_id(brain.id)
    return [_version_to_summary(v) for v in versions]


# ---------------------------------------------------------------------------
# GET /brain/versions/{version_id} — Get one version with rules
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/brain/versions/{version_id}",
    response_model=BrainVersionRead,
)
async def get_version(
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_access),
    ],
) -> BrainVersionRead:
    """Return one BrainVersion including its rules and lifecycle metadata."""
    _, version = brain_version
    return _version_to_read(version)


# ---------------------------------------------------------------------------
# POST /brain/versions — Create a new DRAFT version
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions",
    response_model=BrainVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    body: BrainVersionCreate,
    brain: Annotated[BusinessBrain, Depends(require_brain_modify)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BrainVersionRead:
    """Create a new DRAFT BrainVersion. Requires admin+ role."""
    service = BrainService(db)
    version = await service.create_version(brain.id, config=body.config)
    # Reload with rules relationship
    from app.domain.business.repository import BrainVersionRepository

    version_repo = BrainVersionRepository(db)
    version = await version_repo.get_by_id(version.id)
    return _version_to_read(version)


# ---------------------------------------------------------------------------
# PATCH /brain/versions/{version_id} — Update DRAFT configuration
# ---------------------------------------------------------------------------


@router.patch(
    "/{business_id}/brain/versions/{version_id}",
    response_model=BrainVersionRead,
)
async def update_version(
    body: BrainVersionUpdate,
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_modify),
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BrainVersionRead:
    """Modify a DRAFT version's configuration. Requires admin+ role.

    Immutable versions (REVIEW, APPROVED, ACTIVE, SUPERSEDED) are rejected.
    """
    _, version = brain_version
    service = BrainService(db)

    # Build config dict from set fields, mapping schema field names
    # (e.g. identity_config) to config area names (e.g. identity).
    raw = body.model_dump(exclude_unset=True)
    config = {}
    for key, value in raw.items():
        area_name = key.removesuffix("_config") if key.endswith("_config") else key
        config[area_name] = value
    updated = await service.update_version_config(version.id, config)

    # Reload with rules
    from app.domain.business.repository import BrainVersionRepository

    version_repo = BrainVersionRepository(db)
    updated = await version_repo.get_by_id(updated.id)
    return _version_to_read(updated)


# ---------------------------------------------------------------------------
# POST /brain/versions/{version_id}/rules — Add a rule
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions/{version_id}/rules",
    response_model=BusinessRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_rule(
    body: BusinessRuleCreate,
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_modify),
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessRuleRead:
    """Add a BusinessRule to a DRAFT version. Requires admin+ role."""
    _, version = brain_version
    rule_service = BusinessRuleService(db)
    rule = await rule_service.add_rule(
        brain_version_id=version.id,
        rule_type=body.rule_type,
        name=body.name,
        rule_data=body.rule_data,
        description=body.description,
        priority=body.priority,
    )
    # Refresh to reload attributes expired by the flush
    await db.refresh(rule)
    return BusinessRuleRead.model_validate(rule)


# ---------------------------------------------------------------------------
# POST /brain/versions/{version_id}/rules/{rule_id} — Update a rule
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions/{version_id}/rules/{rule_id}",
    response_model=BusinessRuleRead,
)
async def update_rule(
    body: BusinessRuleUpdate,
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_modify),
    ],
    rule_id: uuid.UUID = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> BusinessRuleRead:
    """Update a BusinessRule within a DRAFT version. Requires admin+ role."""
    _, version = brain_version

    # Verify the rule belongs to this version
    from app.domain.business.repository import BusinessRuleRepository

    rule_repo = BusinessRuleRepository(db)
    rule = await rule_repo.get_by_id(rule_id)
    if rule is None or rule.brain_version_id != version.id:
        raise NotFoundError("Business rule not found in this version")

    rule_service = BusinessRuleService(db)
    updates = body.model_dump(exclude_unset=True)
    updated = await rule_service.update_rule(rule_id, **updates)
    # Refresh to reload attributes expired by the flush
    await db.refresh(updated)
    return BusinessRuleRead.model_validate(updated)


# ---------------------------------------------------------------------------
# DELETE /brain/versions/{version_id}/rules/{rule_id} — Remove a rule
# ---------------------------------------------------------------------------


@router.delete(
    "/{business_id}/brain/versions/{version_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rule(
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_modify),
    ],
    rule_id: uuid.UUID = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> None:
    """Remove a rule from a DRAFT version. Requires admin+ role.

    Does not physically delete — uses soft delete.
    Immutable versions are rejected.
    """
    _, version = brain_version

    # Verify the rule belongs to this version
    from app.domain.business.repository import BusinessRuleRepository

    rule_repo = BusinessRuleRepository(db)
    rule = await rule_repo.get_by_id(rule_id)
    if rule is None or rule.brain_version_id != version.id:
        raise NotFoundError("Business rule not found in this version")

    rule_service = BusinessRuleService(db)
    await rule_service.delete_rule(rule_id)


# ---------------------------------------------------------------------------
# POST /brain/versions/{version_id}/validate — Structural validation
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions/{version_id}/validate",
    response_model=ValidationResultRead,
)
async def validate_version(
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_access),
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ValidationResultRead:
    """Run structural validation on a BrainVersion.

    Uses the Phase 07 structural validator.  Returns structured errors
    that a frontend can use to identify and fix issues.
    """
    _, version = brain_version
    service = BrainService(db)
    result = await service.validate_version(version.id)

    errors = [ValidationErrorDetail(field=e.field, message=e.message, code=e.code) for e in result.errors]
    return ValidationResultRead(
        valid=result.is_valid,
        error_count=len(result.errors),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# POST /brain/versions/{version_id}/transition — Lifecycle transition
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions/{version_id}/transition",
    response_model=BrainVersionTransitionRead,
)
async def transition_version(
    body: BrainVersionTransitionRequest,
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_modify),
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BrainVersionTransitionRead:
    """Perform a lifecycle transition on a BrainVersion.

    Only valid state-machine transitions are permitted.
    Requires admin+ role.
    """
    _, version = brain_version
    previous_status = version.status

    service = BrainService(db)
    target_status = BrainVersionStatus(body.target_status)
    updated = await service.transition_version(version.id, target_status)

    return BrainVersionTransitionRead(
        id=updated.id,
        previous_status=previous_status,
        current_status=updated.status,
        version_number=updated.version_number,
    )


# ---------------------------------------------------------------------------
# POST /brain/versions/{version_id}/approve — Approval
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions/{version_id}/approve",
    response_model=ApprovalResultRead,
)
async def approve_version(
    body: ApprovalRequest,
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    brain: Annotated[BusinessBrain, Depends(require_brain_approve)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalResultRead:
    """Approve a BrainVersion according to the approval policy.

    Requires owner role (per frozen authorization model).
    Approval does NOT automatically activate the version.
    """
    # Resolve the version within this brain
    from app.domain.business.repository import BrainVersionRepository

    version_repo = BrainVersionRepository(db)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.brain_id != brain.id:
        raise NotFoundError("Brain version not found in this business's brain")

    # The user's role is OWNER because require_brain_approve enforces it
    approver_role = BusinessMemberRole.OWNER

    service = BrainService(db)
    updated = await service.approve_version(
        version_id=version.id,
        approver_role=approver_role,
        is_author=True,  # default: self-approval allowed per frozen architecture
    )

    return ApprovalResultRead(
        decision="approved",
        version_id=updated.id,
        version_status=updated.status,
        approver_role=approver_role.value,
        comment=body.comment,
    )


# ---------------------------------------------------------------------------
# POST /brain/versions/{version_id}/activate — Activation
# ---------------------------------------------------------------------------


@router.post(
    "/{business_id}/brain/versions/{version_id}/activate",
    response_model=BusinessBrainRead,
)
async def activate_version(
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    brain: Annotated[BusinessBrain, Depends(require_brain_approve)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessBrainRead:
    """Activate an approved BrainVersion.

    Uses the existing transactional activation with SELECT FOR UPDATE.
    Requires owner role.  Supersedes the previous ACTIVE version.
    """
    # Resolve the version within this brain
    from app.domain.business.repository import BrainVersionRepository

    version_repo = BrainVersionRepository(db)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.brain_id != brain.id:
        raise NotFoundError("Brain version not found in this business's brain")

    service = BrainService(db)
    updated_brain = await service.activate_version(business_id, version.id)

    # Refresh to reload attributes expired by the flush
    await db.refresh(updated_brain)

    return BusinessBrainRead.model_validate(updated_brain)


# ---------------------------------------------------------------------------
# GET /brain/versions/{version_id}/provenance — Provenance/audit
# ---------------------------------------------------------------------------


@router.get(
    "/{business_id}/brain/versions/{version_id}/provenance",
    response_model=ProvenanceRead,
)
async def get_provenance(
    brain_version: Annotated[
        tuple[BusinessBrain, BrainVersion],
        Depends(require_brain_version_access),
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProvenanceRead:
    """Return provenance/evidence for a BrainVersion.

    Constructs provenance entries from the version's lifecycle metadata.
    """
    brain, version = brain_version

    # Build provenance entries from version state
    entries: list[ProvenanceEntryRead] = []

    # Creation entry
    entries.append(
        ProvenanceEntryRead(
            action="version_created",
            timestamp=version.created_at,
            details={
                "version_number": version.version_number,
                "initial_status": "draft",
            },
        )
    )

    # Current status entry
    if version.status != BrainVersionStatus.DRAFT:
        entries.append(
            ProvenanceEntryRead(
                action=f"status_changed_to_{version.status}",
                timestamp=version.updated_at,
                details={
                    "version_number": version.version_number,
                    "current_status": version.status,
                },
            )
        )

    # Active version marker
    if brain.active_version_id == version.id:
        entries.append(
            ProvenanceEntryRead(
                action="version_is_active",
                timestamp=version.updated_at,
                details={
                    "brain_id": str(brain.id),
                    "active_since": str(version.updated_at),
                },
            )
        )

    return ProvenanceRead(
        version_id=version.id,
        brain_id=brain.id,
        version_number=version.version_number,
        status=version.status,
        entries=entries,
    )
