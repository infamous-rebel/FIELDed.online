"""Unit tests for enquiry authorization rules.

Tests the authorization logic for:
- Customer ownership verification
- Business membership verification
- Cross-customer access prevention
- Cross-business access prevention
- Role-based access for business operations
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.enquiry.models import Conversation, Enquiry
from app.domain.enquiry.service import EnquiryService
from app.domain.identity.models import CustomerProfile, User
from app.exceptions import AuthorizationError, NotFoundError, ValidationError


def _make_user(user_id: uuid.UUID | None = None) -> User:
    """Create a mock User for testing."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = f"user-{user.id.hex[:8]}@example.com"
    user.is_active = True
    user.customer_profile = MagicMock(spec=CustomerProfile)
    user.business_memberships = []
    return user


def _make_enquiry(
    *,
    customer_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
    status: str = "submitted",
) -> Enquiry:
    """Create a mock Enquiry for testing."""
    enquiry = MagicMock(spec=Enquiry)
    enquiry.id = uuid.uuid4()
    enquiry.customer_id = customer_id or uuid.uuid4()
    enquiry.business_id = business_id or uuid.uuid4()
    enquiry.service_offer_id = uuid.uuid4()
    enquiry.status = status
    return enquiry


def _make_conversation(
    *,
    enquiry_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> Conversation:
    """Create a mock Conversation for testing."""
    conv = MagicMock(spec=Conversation)
    conv.id = uuid.uuid4()
    conv.enquiry_id = enquiry_id or uuid.uuid4()
    conv.customer_id = customer_id or uuid.uuid4()
    conv.business_id = business_id or uuid.uuid4()
    conv.status = "active"
    return conv


class TestCustomerAuthorization:
    """Test customer-side authorization rules."""

    @pytest.mark.asyncio
    async def test_customer_can_access_own_enquiry(self):
        """Customer can access their own enquiry."""
        user = _make_user()
        enquiry = _make_enquiry(customer_id=user.id)

        session = AsyncMock()
        service = EnquiryService(session)
        service.enquiry_repo.get_by_id = AsyncMock(return_value=enquiry)

        result = await service.get_customer_enquiry(enquiry.id, user.id)
        assert result is enquiry

    @pytest.mark.asyncio
    async def test_customer_cannot_access_other_enquiry(self):
        """Customer cannot access another customer's enquiry."""
        user = _make_user()
        other_customer_id = uuid.uuid4()
        enquiry = _make_enquiry(customer_id=other_customer_id)

        session = AsyncMock()
        service = EnquiryService(session)
        service.enquiry_repo.get_by_id = AsyncMock(return_value=enquiry)

        with pytest.raises(AuthorizationError, match="Not your enquiry"):
            await service.get_customer_enquiry(enquiry.id, user.id)

    @pytest.mark.asyncio
    async def test_customer_enquiry_not_found(self):
        """Accessing a non-existent enquiry raises NotFoundError."""
        user = _make_user()
        fake_id = uuid.uuid4()

        session = AsyncMock()
        service = EnquiryService(session)
        service.enquiry_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await service.get_customer_enquiry(fake_id, user.id)


class TestBusinessAuthorization:
    """Test business-side authorization rules."""

    @pytest.mark.asyncio
    async def test_business_can_access_own_enquiry(self):
        """Business can access enquiries belonging to them."""
        business_id = uuid.uuid4()
        enquiry = _make_enquiry(business_id=business_id)

        session = AsyncMock()
        service = EnquiryService(session)
        service.enquiry_repo.get_by_id = AsyncMock(return_value=enquiry)

        result = await service.get_business_enquiry(enquiry.id, business_id)
        assert result is enquiry

    @pytest.mark.asyncio
    async def test_business_cannot_access_other_enquiry(self):
        """Business cannot access enquiries from another business."""
        business_id = uuid.uuid4()
        other_business_id = uuid.uuid4()
        enquiry = _make_enquiry(business_id=other_business_id)

        session = AsyncMock()
        service = EnquiryService(session)
        service.enquiry_repo.get_by_id = AsyncMock(return_value=enquiry)

        with pytest.raises(AuthorizationError, match="does not belong"):
            await service.get_business_enquiry(enquiry.id, business_id)


class TestConversationAuthorization:
    """Test conversation access authorization."""

    @pytest.mark.asyncio
    async def test_verify_customer_access_success(self):
        """Customer can access their own conversation."""
        user = _make_user()
        conv = _make_conversation(customer_id=user.id)

        session = AsyncMock()
        service = EnquiryService(session)

        # Should not raise
        await service.verify_customer_access(conv, user.id)

    @pytest.mark.asyncio
    async def test_verify_customer_access_denied(self):
        """Customer cannot access another's conversation."""
        user = _make_user()
        other_id = uuid.uuid4()
        conv = _make_conversation(customer_id=other_id)

        session = AsyncMock()
        service = EnquiryService(session)

        with pytest.raises(AuthorizationError):
            await service.verify_customer_access(conv, user.id)

    @pytest.mark.asyncio
    async def test_verify_business_access_success(self):
        """Business can access their own conversation."""
        business_id = uuid.uuid4()
        conv = _make_conversation(business_id=business_id)

        session = AsyncMock()
        service = EnquiryService(session)

        await service.verify_business_access(conv, business_id)

    @pytest.mark.asyncio
    async def test_verify_business_access_denied(self):
        """Business cannot access another business's conversation."""
        business_id = uuid.uuid4()
        other_id = uuid.uuid4()
        conv = _make_conversation(business_id=other_id)

        session = AsyncMock()
        service = EnquiryService(session)

        with pytest.raises(AuthorizationError):
            await service.verify_business_access(conv, business_id)


class TestMessageAuthorization:
    """Test message sending authorization rules."""

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        """Empty message content is rejected."""
        conv = _make_conversation()
        user = _make_user()

        session = AsyncMock()
        service = EnquiryService(session)

        with pytest.raises(ValidationError, match="cannot be empty"):
            await service.send_message(
                conversation=conv,
                sender=user,
                sender_type="customer",
                content="",
            )

    @pytest.mark.asyncio
    async def test_whitespace_message_rejected(self):
        """Whitespace-only message content is rejected."""
        conv = _make_conversation()
        user = _make_user()

        session = AsyncMock()
        service = EnquiryService(session)

        with pytest.raises(ValidationError, match="cannot be empty"):
            await service.send_message(
                conversation=conv,
                sender=user,
                sender_type="customer",
                content="   ",
            )
