"""Commercial Policy repository.

Database access for CommercialPolicy entities.
All queries enforce soft-delete filtering (deleted_at IS NULL).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.commercial_policy.models import CommercialPolicy


class CommercialPolicyRepository:
    """Data access for CommercialPolicy entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, policy_id: uuid.UUID) -> CommercialPolicy | None:
        """Fetch a policy by ID."""
        result = await self.session.execute(
            select(CommercialPolicy).where(
                CommercialPolicy.id == policy_id,
                CommercialPolicy.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, policy: CommercialPolicy) -> CommercialPolicy:
        """Persist a new policy."""
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def update(self, policy: CommercialPolicy) -> CommercialPolicy:
        """Update an existing policy."""
        await self.session.flush()
        return policy

    async def list_all(
        self,
        *,
        scope: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CommercialPolicy]:
        """List policies with optional filters."""
        stmt = select(CommercialPolicy).where(
            CommercialPolicy.deleted_at.is_(None),
        )
        if scope:
            stmt = stmt.where(CommercialPolicy.scope == scope)
        if status:
            stmt = stmt.where(CommercialPolicy.status == status)
        stmt = stmt.order_by(CommercialPolicy.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_effective_policies(
        self,
        *,
        business_id: uuid.UUID,
        category_id: uuid.UUID | None = None,
        promotion_code: str | None = None,
        at_time: datetime | None = None,
    ) -> list[CommercialPolicy]:
        """Resolve all potentially applicable active policies.

        Returns policies ordered by precedence (highest first).
        The caller (CommercialPolicyService) picks the winner.
        """
        now = at_time or datetime.now()

        # Common time-window filter: effective_from <= now AND
        # (effective_until IS NULL OR effective_until > now)
        time_filter = and_(
            CommercialPolicy.effective_from <= now,
            or_(
                CommercialPolicy.effective_until.is_(None),
                CommercialPolicy.effective_until > now,
            ),
        )

        # Build scope-specific filters (OR across tiers)
        scope_filters = [
            # GLOBAL_DEFAULT — always applicable
            and_(
                CommercialPolicy.scope == "global_default",
                CommercialPolicy.status == "active",
                CommercialPolicy.is_active.is_(True),
            ),
            # CATEGORY_DEFAULT — matches category_id
            and_(
                CommercialPolicy.scope == "category_default",
                CommercialPolicy.status == "active",
                CommercialPolicy.is_active.is_(True),
                CommercialPolicy.category_id == category_id,
            ),
            # BUSINESS_PLAN — matches business_id
            and_(
                CommercialPolicy.scope == "business_plan",
                CommercialPolicy.status == "active",
                CommercialPolicy.is_active.is_(True),
                CommercialPolicy.business_id == business_id,
            ),
            # PROMOTION — matches business_id OR is global promotion
            and_(
                CommercialPolicy.scope == "promotion",
                CommercialPolicy.status == "active",
                CommercialPolicy.is_active.is_(True),
                or_(
                    CommercialPolicy.business_id == business_id,
                    CommercialPolicy.business_id.is_(None),
                ),
                # If a promotion_code is supplied, match it; otherwise
                # only match promotions without a code requirement.
                or_(
                    CommercialPolicy.promotion_code.is_(None),
                    CommercialPolicy.promotion_code == promotion_code,
                )
                if promotion_code
                else CommercialPolicy.promotion_code.is_(None),
            ),
            # BUSINESS_SPECIFIC — matches business_id exactly
            and_(
                CommercialPolicy.scope == "business_specific",
                CommercialPolicy.status == "active",
                CommercialPolicy.is_active.is_(True),
                CommercialPolicy.business_id == business_id,
            ),
        ]

        stmt = (
            select(CommercialPolicy)
            .where(
                CommercialPolicy.deleted_at.is_(None),
                time_filter,
                or_(*scope_filters),
            )
            .order_by(CommercialPolicy.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_global_default(self, at_time: datetime | None = None) -> CommercialPolicy | None:
        """Return the currently effective global default policy."""
        now = at_time or datetime.now()
        stmt = (
            select(CommercialPolicy)
            .where(
                CommercialPolicy.deleted_at.is_(None),
                CommercialPolicy.scope == "global_default",
                CommercialPolicy.status == "active",
                CommercialPolicy.is_active.is_(True),
                CommercialPolicy.effective_from <= now,
                or_(
                    CommercialPolicy.effective_until.is_(None),
                    CommercialPolicy.effective_until > now,
                ),
            )
            .order_by(CommercialPolicy.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_next_version(self, scope: str, name: str) -> int:
        """Get the next version number for a given scope+name."""
        stmt = (
            select(CommercialPolicy.version)
            .where(
                CommercialPolicy.scope == scope,
                CommercialPolicy.name == name,
                CommercialPolicy.deleted_at.is_(None),
            )
            .order_by(CommercialPolicy.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        current = result.scalar_one_or_none()
        return (current or 0) + 1
