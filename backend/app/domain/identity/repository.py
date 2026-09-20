"""Identity domain repository.

Provides database access for User, CustomerProfile, Business, BusinessMember.
All queries are tenant-aware where applicable.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.identity.models import (
    Business,
    BusinessMember,
    CustomerProfile,
    User,
)


class UserRepository:
    """Data access for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by ID, including relationships."""
        result = await self.session.execute(
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .options(
                selectinload(User.customer_profile),
                selectinload(User.business_memberships),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        result = await self.session.execute(
            select(User)
            .where(User.email == email, User.deleted_at.is_(None))
            .options(
                selectinload(User.customer_profile),
                selectinload(User.business_memberships),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Persist a new user."""
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User) -> User:
        """Update an existing user."""
        await self.session.flush()
        return user


class CustomerProfileRepository:
    """Data access for CustomerProfile entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> CustomerProfile | None:
        """Fetch a customer profile by user ID."""
        result = await self.session.execute(
            select(CustomerProfile).where(
                CustomerProfile.user_id == user_id,
                CustomerProfile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, profile: CustomerProfile) -> CustomerProfile:
        """Persist a new customer profile."""
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def update(self, profile: CustomerProfile) -> CustomerProfile:
        """Update an existing customer profile."""
        await self.session.flush()
        return profile


class BusinessRepository:
    """Data access for Business entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, business_id: uuid.UUID) -> Business | None:
        """Fetch a business by ID."""
        result = await self.session.execute(
            select(Business)
            .where(Business.id == business_id, Business.deleted_at.is_(None))
            .options(
                selectinload(Business.members),
                selectinload(Business.profile),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Business | None:
        """Fetch a business by public slug."""
        result = await self.session.execute(
            select(Business)
            .where(Business.slug == slug, Business.deleted_at.is_(None))
            .options(selectinload(Business.profile))
        )
        return result.scalar_one_or_none()

    async def create(self, business: Business) -> Business:
        """Persist a new business."""
        self.session.add(business)
        await self.session.flush()
        return business


class BusinessMemberRepository:
    """Data access for BusinessMember entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_and_business(
        self, user_id: uuid.UUID, business_id: uuid.UUID
    ) -> BusinessMember | None:
        """Fetch a specific membership."""
        result = await self.session.execute(
            select(BusinessMember).where(
                BusinessMember.user_id == user_id,
                BusinessMember.business_id == business_id,
                BusinessMember.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> list[BusinessMember]:
        """Fetch all memberships for a user."""
        result = await self.session.execute(
            select(BusinessMember)
            .where(
                BusinessMember.user_id == user_id,
                BusinessMember.deleted_at.is_(None),
            )
            .options(selectinload(BusinessMember.business))
        )
        return list(result.scalars().all())

    async def get_by_business_id(self, business_id: uuid.UUID) -> list[BusinessMember]:
        """Fetch all members of a business."""
        result = await self.session.execute(
            select(BusinessMember)
            .where(
                BusinessMember.business_id == business_id,
                BusinessMember.deleted_at.is_(None),
            )
            .options(selectinload(BusinessMember.user))
        )
        return list(result.scalars().all())

    async def create(self, member: BusinessMember) -> BusinessMember:
        """Persist a new business membership."""
        self.session.add(member)
        await self.session.flush()
        return member
