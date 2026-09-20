"""Business Brain authorization dependencies for future API endpoints.

Provides reusable FastAPI dependencies that enforce tenant isolation
and role-based access for all Brain operations.

These dependencies follow the same patterns used by existing enquiry
and business endpoints:
- Business membership is verified server-side
- Role hierarchy is enforced (owner > admin > staff)
- Cross-tenant access is impossible by design

Usage in future Brain API endpoints:

    @router.get("/brains/{business_id}")
    async def get_brain(
        brain: Annotated[BusinessBrain, Depends(require_brain_access)],
    ):
        ...

    @router.post("/brains/{business_id}/versions")
    async def create_version(
        brain: Annotated[BusinessBrain, Depends(require_brain_modify)],
    ):
        ...

    @router.post("/brains/{business_id}/versions/{version_id}/approve")
    async def approve_version(
        brain: Annotated[BusinessBrain, Depends(require_brain_approve)],
    ):
        ...
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.business.models import BusinessBrain
from app.domain.business.repository import BusinessBrainRepository
from app.domain.common.enums import BusinessMemberRole
from app.domain.identity.models import Business, BusinessMember, User
from app.exceptions import AuthorizationError, NotFoundError
from app.security.authorization import get_current_user


# ---------------------------------------------------------------------------
# Role hierarchy (consistent with rest of FIELDed)
# ---------------------------------------------------------------------------

_ROLE_LEVELS: dict[BusinessMemberRole, int] = {
    BusinessMemberRole.OWNER: 3,
    BusinessMemberRole.ADMIN: 2,
    BusinessMemberRole.STAFF: 1,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _resolve_brain_with_membership(
    business_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    minimum_role: BusinessMemberRole,
) -> tuple[BusinessBrain, BusinessMember]:
    """Resolve a BusinessBrain and verify the user has the required role.

    This is the core tenant-isolation function.  It:
    1. Verifies the business exists
    2. Verifies the user is a member of that business
    3. Verifies the user meets the minimum role requirement
    4. Returns the brain (creating it if needed) and the membership

    Raises:
        NotFoundError: If the business does not exist
        AuthorizationError: If the user is not a member or lacks the role
    """
    # 1. Verify business exists
    from sqlalchemy import select
    result = await db.execute(
        select(Business).where(
            Business.id == business_id,
            Business.deleted_at.is_(None),
        )
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Business not found")

    # 2. Verify user is a member of THIS business (tenant isolation)
    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.user_id == user.id,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise AuthorizationError("Not a member of this business")

    # 3. Verify role level
    member_level = _ROLE_LEVELS.get(BusinessMemberRole(membership.role), 0)
    required_level = _ROLE_LEVELS.get(minimum_role, 0)
    if member_level < required_level:
        raise AuthorizationError(
            f"Requires {minimum_role.value} role or higher "
            f"(current: {membership.role})"
        )

    # 4. Resolve brain (get or create)
    brain_repo = BusinessBrainRepository(db)
    brain = await brain_repo.get_by_business_id(business_id)
    if brain is None:
        brain = BusinessBrain(business_id=business_id)
        brain = await brain_repo.create(brain)

    return brain, membership


# ---------------------------------------------------------------------------
# Reusable FastAPI dependencies
# ---------------------------------------------------------------------------

def _make_brain_dependency(minimum_role: BusinessMemberRole):
    """Factory for Brain authorization dependencies at a given role level."""

    async def _dependency(
        business_id: uuid.UUID,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> BusinessBrain:
        brain, _ = await _resolve_brain_with_membership(
            business_id, user, db, minimum_role,
        )
        return brain

    return _dependency


async def _dependency_with_membership(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    minimum_role: BusinessMemberRole,
) -> tuple[BusinessBrain, BusinessMember]:
    """Resolve brain + membership for endpoints that need both."""
    return await _resolve_brain_with_membership(
        business_id, user, db, minimum_role,
    )


# ---------------------------------------------------------------------------
# Public dependency functions
# ---------------------------------------------------------------------------

# READ access: any business member (staff+) can read the Brain
require_brain_access = _make_brain_dependency(BusinessMemberRole.STAFF)

# MODIFY access: admin+ can create/edit versions and rules
require_brain_modify = _make_brain_dependency(BusinessMemberRole.ADMIN)

# APPROVE/ACTIVATE access: owner only
require_brain_approve = _make_brain_dependency(BusinessMemberRole.OWNER)


# ---------------------------------------------------------------------------
# Version-level authorization
# ---------------------------------------------------------------------------

async def require_brain_version_access(
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> tuple[BusinessBrain, "BrainVersion"]:
    """Resolve a BrainVersion within a tenant-scoped Brain.

    Ensures the version belongs to the referenced business's brain.
    """
    from app.domain.business.repository import BrainVersionRepository

    brain = await require_brain_access(business_id, user, db)

    version_repo = BrainVersionRepository(db)
    version = await version_repo.get_by_id(version_id)
    if version is None:
        raise NotFoundError(f"Brain version {version_id} not found")

    if version.brain_id != brain.id:
        raise AuthorizationError(
            "Brain version does not belong to this business's brain"
        )

    return brain, version


async def require_brain_version_modify(
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> tuple[BusinessBrain, "BrainVersion"]:
    """Resolve a BrainVersion with admin+ role for modification."""
    from app.domain.business.repository import BrainVersionRepository

    brain = await require_brain_modify(business_id, user, db)

    version_repo = BrainVersionRepository(db)
    version = await version_repo.get_by_id(version_id)
    if version is None:
        raise NotFoundError(f"Brain version {version_id} not found")

    if version.brain_id != brain.id:
        raise AuthorizationError(
            "Brain version does not belong to this business's brain"
        )

    return brain, version
