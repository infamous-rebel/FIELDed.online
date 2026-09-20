"""Identity domain service.

Contains business logic for user registration, profile management,
and business membership operations.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import (
    Business,
    BusinessMember,
    CustomerProfile,
    User,
)
from app.domain.identity.repository import (
    BusinessMemberRepository,
    BusinessRepository,
    CustomerProfileRepository,
    UserRepository,
)
from app.exceptions import ConflictError, NotFoundError
from app.security.password import hash_password


class UserService:
    """User registration and management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)

    async def register_user(self, email: str, password: str) -> User:
        """Register a new user with hashed password."""
        existing = await self.user_repo.get_by_email(email)
        if existing is not None:
            raise ConflictError(f"User with email {email} already exists")

        user = User(
            email=email,
            hashed_password=hash_password(password),
        )
        return await self.user_repo.create(user)

    async def get_user(self, user_id: uuid.UUID) -> User:
        """Fetch a user by ID."""
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user


class CustomerProfileService:
    """Customer profile management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profile_repo = CustomerProfileRepository(session)

    async def create_profile(
        self,
        user_id: uuid.UUID,
        first_name: str,
        last_name: str,
        **kwargs: str | None,
    ) -> CustomerProfile:
        """Create a customer profile for a user."""
        existing = await self.profile_repo.get_by_user_id(user_id)
        if existing is not None:
            raise ConflictError("Customer profile already exists for this user")

        profile = CustomerProfile(
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            **kwargs,
        )
        return await self.profile_repo.create(profile)


class BusinessService:
    """Business creation and membership management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.business_repo = BusinessRepository(session)
        self.member_repo = BusinessMemberRepository(session)

    async def create_business(
        self,
        name: str,
        slug: str,
        owner_user_id: uuid.UUID,
    ) -> Business:
        """Create a new business and assign the creator as owner."""
        business = Business(name=name, slug=slug)
        await self.business_repo.create(business)

        # Assign creator as owner
        member = BusinessMember(
            user_id=owner_user_id,
            business_id=business.id,
            role="owner",
        )
        await self.member_repo.create(member)

        return business
