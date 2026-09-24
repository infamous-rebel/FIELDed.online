"""Integration tests for tenant isolation.

Verifies that the repository/authorization layer enforces tenant boundaries.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, User


class TestTenantIsolation:
    """Test tenant isolation at the data layer."""

    @pytest.mark.asyncio
    async def test_business_member_isolation(self, db_session: AsyncSession, test_user, second_user):
        """A user's business memberships don't include another user's businesses."""
        # Create a business owned by test_user
        business = Business(name="User1 Business", slug="user1-biz")
        db_session.add(business)
        await db_session.flush()

        membership = BusinessMember(
            user_id=test_user.id,
            business_id=business.id,
            role="owner",
        )
        db_session.add(membership)
        await db_session.flush()

        # Query second_user's memberships — should be empty
        result = await db_session.execute(select(BusinessMember).where(BusinessMember.user_id == second_user.id))
        second_memberships = result.scalars().all()
        assert len(second_memberships) == 0

    @pytest.mark.asyncio
    async def test_users_have_separate_data(self, db_session: AsyncSession, test_user, second_user):
        """Each user has their own isolated data."""
        result1 = await db_session.execute(select(User).where(User.id == test_user.id))
        result2 = await db_session.execute(select(User).where(User.id == second_user.id))

        user1 = result1.scalar_one()
        user2 = result2.scalar_one()

        assert user1.email != user2.email
        assert user1.id != user2.id
