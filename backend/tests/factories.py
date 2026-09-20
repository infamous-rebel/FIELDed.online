"""Test data factories.

Provides factory functions for creating domain model instances in tests.
"""

from __future__ import annotations

import uuid

from app.domain.business.models import BrainVersion, BusinessBrain, BusinessRule
from app.domain.identity.models import (
    Business,
    BusinessMember,
    BusinessProfile,
    CustomerProfile,
    User,
)
from app.domain.services.models import ServiceCategory, ServiceOffer
from app.security.password import hash_password


def user_factory(
    email: str | None = None,
    password: str = "testpassword123",
    is_active: bool = True,
) -> User:
    """Create a User instance for testing."""
    return User(
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password(password),
        is_active=is_active,
    )


def customer_profile_factory(
    user_id: uuid.UUID,
    first_name: str = "Test",
    last_name: str = "Customer",
) -> CustomerProfile:
    """Create a CustomerProfile instance for testing."""
    return CustomerProfile(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
    )


def business_factory(
    name: str | None = None,
    slug: str | None = None,
) -> Business:
    """Create a Business instance for testing."""
    unique = uuid.uuid4().hex[:8]
    return Business(
        name=name or f"Test Business {unique}",
        slug=slug or f"test-business-{unique}",
    )


def business_member_factory(
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    role: str = "owner",
) -> BusinessMember:
    """Create a BusinessMember instance for testing."""
    return BusinessMember(
        user_id=user_id,
        business_id=business_id,
        role=role,
    )


def business_profile_factory(
    business_id: uuid.UUID,
    description: str = "A test business",
) -> BusinessProfile:
    """Create a BusinessProfile instance for testing."""
    return BusinessProfile(
        business_id=business_id,
        description=description,
    )


def business_brain_factory(
    business_id: uuid.UUID,
) -> BusinessBrain:
    """Create a BusinessBrain instance for testing."""
    return BusinessBrain(business_id=business_id)


def brain_version_factory(
    brain_id: uuid.UUID,
    version_number: int = 1,
    status: str = "draft",
) -> BrainVersion:
    """Create a BrainVersion instance for testing."""
    return BrainVersion(
        brain_id=brain_id,
        version_number=version_number,
        status=status,
    )


def business_rule_factory(
    brain_version_id: uuid.UUID,
    rule_type: str = "pricing",
    name: str | None = None,
) -> BusinessRule:
    """Create a BusinessRule instance for testing."""
    return BusinessRule(
        brain_version_id=brain_version_id,
        rule_type=rule_type,
        name=name or f"Test {rule_type} rule",
        rule_data={"test": True},
    )


def service_category_factory(
    name: str | None = None,
    slug: str | None = None,
) -> ServiceCategory:
    """Create a ServiceCategory instance for testing."""
    unique = uuid.uuid4().hex[:8]
    return ServiceCategory(
        name=name or f"Test Category {unique}",
        slug=slug or f"test-category-{unique}",
    )


def service_offer_factory(
    business_id: uuid.UUID,
    name: str | None = None,
    slug: str | None = None,
) -> ServiceOffer:
    """Create a ServiceOffer instance for testing."""
    unique = uuid.uuid4().hex[:8]
    return ServiceOffer(
        business_id=business_id,
        name=name or f"Test Service {unique}",
        slug=slug or f"test-service-{unique}",
    )
