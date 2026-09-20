"""Business Brain domain repository.

Provides database access for BusinessBrain, BrainVersion, BusinessRule.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.business.models import BusinessBrain, BrainVersion, BusinessRule
from app.domain.common.enums import BrainVersionStatus


class BusinessBrainRepository:
    """Data access for BusinessBrain entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_business_id(self, business_id: uuid.UUID) -> BusinessBrain | None:
        """Fetch the brain for a business."""
        result = await self.session.execute(
            select(BusinessBrain)
            .where(
                BusinessBrain.business_id == business_id,
                BusinessBrain.deleted_at.is_(None),
            )
            .options(selectinload(BusinessBrain.versions))
        )
        return result.scalar_one_or_none()

    async def get_by_business_id_for_update(
        self, business_id: uuid.UUID
    ) -> BusinessBrain | None:
        """Fetch the brain for a business with pessimistic lock (SELECT FOR UPDATE).

        Prevents concurrent activation of brain versions for the same business.
        """
        result = await self.session.execute(
            select(BusinessBrain)
            .where(
                BusinessBrain.business_id == business_id,
                BusinessBrain.deleted_at.is_(None),
            )
            .options(selectinload(BusinessBrain.versions))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create(self, brain: BusinessBrain) -> BusinessBrain:
        """Persist a new business brain."""
        self.session.add(brain)
        await self.session.flush()
        return brain

    async def update_active_version(
        self, brain: BusinessBrain, version_id: uuid.UUID | None
    ) -> BusinessBrain:
        """Set the active version for a brain."""
        brain.active_version_id = version_id
        await self.session.flush()
        return brain


class BrainVersionRepository:
    """Data access for BrainVersion entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, version_id: uuid.UUID) -> BrainVersion | None:
        """Fetch a brain version by ID."""
        result = await self.session.execute(
            select(BrainVersion)
            .where(
                BrainVersion.id == version_id,
                BrainVersion.deleted_at.is_(None),
            )
            .options(selectinload(BrainVersion.rules))
        )
        return result.scalar_one_or_none()

    async def get_by_brain_id(
        self, brain_id: uuid.UUID
    ) -> list[BrainVersion]:
        """Fetch all versions for a brain, ordered by version number desc."""
        result = await self.session.execute(
            select(BrainVersion)
            .where(
                BrainVersion.brain_id == brain_id,
                BrainVersion.deleted_at.is_(None),
            )
            .options(selectinload(BrainVersion.rules))
            .order_by(BrainVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_next_version_number(self, brain_id: uuid.UUID) -> int:
        """Get the next version number for a brain."""
        result = await self.session.execute(
            select(func.max(BrainVersion.version_number)).where(
                BrainVersion.brain_id == brain_id,
            )
        )
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1

    async def create(self, version: BrainVersion) -> BrainVersion:
        """Persist a new brain version."""
        self.session.add(version)
        await self.session.flush()
        return version

    async def update(self, version: BrainVersion) -> BrainVersion:
        """Update an existing brain version."""
        await self.session.flush()
        return version

    async def get_active_by_brain_id(
        self, brain_id: uuid.UUID
    ) -> BrainVersion | None:
        """Find the currently ACTIVE version for a brain, if any."""
        result = await self.session.execute(
            select(BrainVersion)
            .where(
                BrainVersion.brain_id == brain_id,
                BrainVersion.status == BrainVersionStatus.ACTIVE,
                BrainVersion.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


class BusinessRuleRepository:
    """Data access for BusinessRule entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, rule_id: uuid.UUID) -> BusinessRule | None:
        """Fetch a single business rule by ID."""
        result = await self.session.execute(
            select(BusinessRule)
            .where(
                BusinessRule.id == rule_id,
                BusinessRule.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_brain_version_id(
        self, brain_version_id: uuid.UUID
    ) -> list[BusinessRule]:
        """Fetch all rules for a brain version."""
        result = await self.session.execute(
            select(BusinessRule)
            .where(
                BusinessRule.brain_version_id == brain_version_id,
                BusinessRule.deleted_at.is_(None),
            )
            .order_by(BusinessRule.priority.desc())
        )
        return list(result.scalars().all())

    async def create(self, rule: BusinessRule) -> BusinessRule:
        """Persist a new business rule."""
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def update(self, rule: BusinessRule) -> BusinessRule:
        """Update an existing business rule."""
        await self.session.flush()
        return rule

    async def delete(self, rule: BusinessRule) -> None:
        """Soft-delete a business rule."""
        from datetime import datetime, timezone

        rule.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
