"""Authorization logic — RBAC and tenant isolation.

This module provides FastAPI dependencies for:
- Resolving the current authenticated user
- Resolving the tenant context
- Enforcing role-based access control
- Enforcing tenant isolation at the repository level
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db_session
from app.domain.common.enums import BusinessMemberRole
from app.domain.identity.models import Business, BusinessMember, CustomerProfile, User
from app.exceptions import AuthenticationError, AuthorizationError, TenantIsolationError
from app.security.jwt import decode_token


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Resolve the current authenticated user from the Authorization header.

    Raises:
        AuthenticationError: If no valid token is provided.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    token = auth_header.split(" ", 1)[1]
    settings = request.app.state.settings
    claims = decode_token(settings, token)

    if claims.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    user_id = claims.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing subject")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise AuthenticationError("Invalid token subject")

    result = await db.execute(
        select(User)
        .options(
            selectinload(User.customer_profile),
            selectinload(User.business_memberships),
        )
        .where(User.id == user_uuid, User.is_active.is_(True), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found or inactive")

    return user


async def get_optional_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User | None:
    """Try to resolve the current user. Returns None if not authenticated."""
    try:
        return await get_current_user(request, db)
    except AuthenticationError:
        return None


async def require_customer(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the current user has a customer profile.

    Raises:
        AuthorizationError: If the user is not a customer.
    """
    if user.customer_profile is None:
        raise AuthorizationError("Customer profile required")
    return user


async def require_business_member(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the current user is a member of at least one business.

    Raises:
        AuthorizationError: If the user has no business memberships.
    """
    if not user.business_memberships:
        raise AuthorizationError("Business membership required")
    return user


def require_business_role(minimum_role: BusinessMemberRole):
    """Create a dependency that checks business role for a specific business.

    Args:
        minimum_role: The minimum role required (owner > admin > staff).
    """
    role_hierarchy = {
        BusinessMemberRole.OWNER: 3,
        BusinessMemberRole.ADMIN: 2,
        BusinessMemberRole.STAFF: 1,
    }
    minimum_level = role_hierarchy.get(minimum_role, 0)

    async def _check_role(
        business_id: uuid.UUID,
        user: Annotated[User, Depends(get_current_user)],
    ) -> BusinessMember:
        for membership in user.business_memberships:
            if membership.business_id == business_id:
                member_level = role_hierarchy.get(
                    BusinessMemberRole(membership.role), 0
                )
                if member_level >= minimum_level:
                    return membership
                raise AuthorizationError(
                    f"Requires {minimum_role.value} role or higher"
                )
        raise TenantIsolationError("Not a member of this business")

    return _check_role


def tenant_scope(model_class):
    """Create a tenant-scoped query helper.

    Ensures that queries only return records belonging to the
    authenticated user's tenant scope.

    For customers: filters by customer_id == user.id.
    For business members: filters by business_id in member's business_ids.

    The model must have a `customer_id` column (for customer-scoped models)
    or a `business_id` column (for business-scoped models).  If neither
    column exists the dependency raises AuthorizationError.
    """
    has_customer_id = hasattr(model_class, "customer_id")
    has_business_id = hasattr(model_class, "business_id")

    async def _get_tenant_scoped(
        record_id: uuid.UUID,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db_session)],
    ):
        """Fetch a record with tenant isolation.

        For customers: only their own records (customer_id match).
        For business members: records belonging to their business.
        """
        # Determine tenant scope from user
        if user.customer_profile and has_customer_id:
            # Customer can only access their own records
            stmt = select(model_class).where(
                model_class.id == record_id,
                model_class.customer_id == user.id,
                model_class.deleted_at.is_(None),
            )
        elif user.business_memberships and has_business_id:
            business_ids = [m.business_id for m in user.business_memberships]
            stmt = select(model_class).where(
                model_class.id == record_id,
                model_class.business_id.in_(business_ids),
                model_class.deleted_at.is_(None),
            )
        elif user.customer_profile and has_business_id:
            # User has a customer profile but the model is business-scoped.
            # Check if the user also has business memberships.
            if not user.business_memberships:
                raise AuthorizationError("Resource not found or access denied")
            business_ids = [m.business_id for m in user.business_memberships]
            stmt = select(model_class).where(
                model_class.id == record_id,
                model_class.business_id.in_(business_ids),
                model_class.deleted_at.is_(None),
            )
        else:
            raise AuthorizationError("No tenant scope")

        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            raise AuthorizationError("Resource not found or access denied")

        return record

    return _get_tenant_scoped
