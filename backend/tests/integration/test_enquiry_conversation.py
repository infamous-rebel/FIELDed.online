"""Integration tests for Enquiry messaging, conversation access, and lifecycle.

Requires PostgreSQL test database.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User
from app.domain.services.models import ServiceOffer


@pytest.mark.integration
class TestEnquiryConversation:
    """Test conversation and messaging operations."""

    @pytest_asyncio.fixture
    async def enquiry_setup(self, db_session: AsyncSession, second_user: User):
        """Create a business with an active offer, and a customer enquiry."""
        business = Business(name="Conv Biz", slug=f"conv-biz-{id(self)}", status="active")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=second_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(
            business_id=business.id,
            public_status="active",
        )
        db_session.add(profile)

        offer = ServiceOffer(
            business_id=business.id,
            name="Conv Service",
            slug=f"conv-service-{id(self)}",
            status="active",
        )
        db_session.add(offer)
        await db_session.flush()

        return business, offer

    async def _create_enquiry(self, client: AsyncClient, auth_headers: dict, business, offer) -> str:
        """Helper to create an enquiry and return its ID."""
        response = await client.post(
            f"/api/v1/enquiries/{business.id}/enquiries",
            headers=auth_headers,
            json={
                "service_offer_id": str(offer.id),
                "subject": "Conv test",
                "message": "Initial enquiry message.",
            },
        )
        assert response.status_code == 201
        return response.json()["id"]

    # --- Conversation access ---

    async def test_customer_get_conversation(
        self,
        client: AsyncClient,
        auth_headers: dict,
        enquiry_setup,
    ):
        """Customer can access the conversation for their enquiry."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.get(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/conversation",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enquiry_id"] == enquiry_id
        assert "messages" in data

    async def test_cross_customer_conversation_access_denied(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Customer B cannot access Customer A's conversation."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.get(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/conversation",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

    # --- Messaging ---

    async def test_customer_send_message(
        self,
        client: AsyncClient,
        auth_headers: dict,
        enquiry_setup,
    ):
        """Customer can send a message in their enquiry conversation."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.post(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/messages",
            headers=auth_headers,
            json={"content": "Hello, I need more details."},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Hello, I need more details."
        assert data["sender_type"] == "customer"

    async def test_business_send_message(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Business member can send a message in an enquiry conversation."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/messages",
            headers=second_auth_headers,
            json={"content": "Thank you for your enquiry. We will help."},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Thank you for your enquiry. We will help."
        assert data["sender_type"] == "business"

    async def test_empty_message_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        enquiry_setup,
    ):
        """Empty message content is rejected."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.post(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/messages",
            headers=auth_headers,
            json={"content": ""},
        )
        assert response.status_code == 422  # Validation error

    async def test_cross_conversation_message_denied(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Customer cannot send messages to another customer's conversation."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        # second_user tries to send a message to test_user's conversation
        response = await client.post(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/messages",
            headers=second_auth_headers,
            json={"content": "Intruder message"},
        )
        assert response.status_code == 403

    async def test_non_member_business_message_denied(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Non-member cannot send messages to business enquiries."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        # test_user (not a member of the business) tries to send as business
        response = await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/messages",
            headers=auth_headers,
            json={"content": "Non-member message"},
        )
        assert response.status_code == 403

    # --- Lifecycle transitions ---

    async def test_business_transition_enquiry(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Business member can transition an enquiry (SUBMITTED -> RECEIVED)."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/transition",
            headers=second_auth_headers,
            json={"target_status": "received"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "received"

    async def test_customer_cancel_enquiry(
        self,
        client: AsyncClient,
        auth_headers: dict,
        enquiry_setup,
    ):
        """Customer can cancel their own enquiry."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.post(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/transition",
            headers=auth_headers,
            json={"target_status": "cancelled"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    async def test_invalid_transition_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Invalid lifecycle transitions are rejected."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        # SUBMITTED -> IN_REVIEW is not valid (must go through RECEIVED first)
        response = await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/transition",
            headers=second_auth_headers,
            json={"target_status": "in_review"},
        )
        assert response.status_code == 422  # StateTransitionError

    async def test_terminal_state_no_transitions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Once declined, no further transitions are allowed."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        # SUBMITTED -> RECEIVED -> DECLINED
        await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/transition",
            headers=second_auth_headers,
            json={"target_status": "received"},
        )
        await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/transition",
            headers=second_auth_headers,
            json={"target_status": "declined"},
        )

        # DECLINED -> anything should fail
        response = await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/transition",
            headers=second_auth_headers,
            json={"target_status": "in_review"},
        )
        assert response.status_code == 422

    # --- Business enquiry access ---

    async def test_business_list_enquiries(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Business member can list enquiries for their business."""
        business, offer = enquiry_setup
        await self._create_enquiry(client, auth_headers, business, offer)

        response = await client.get(
            f"/api/v1/businesses/{business.id}/enquiries",
            headers=second_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_cross_business_enquiry_access_denied(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
        db_session: AsyncSession,
    ):
        """Business B cannot access enquiries from Business A."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        # Create a separate business for the "intruder"
        other_biz = Business(name="Other Biz", slug=f"other-biz-{id(self)}", status="active")
        db_session.add(other_biz)
        await db_session.flush()

        # test_user is not a member of other_biz, but second_user is the owner
        # of the original business. Test with test_user accessing the business enquiry.
        response = await client.get(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}",
            headers=auth_headers,  # test_user is NOT a member of this business
        )
        assert response.status_code == 403

    # --- Message listing ---

    async def test_list_messages_in_conversation(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        enquiry_setup,
    ):
        """Both customer and business can list messages in the conversation."""
        business, offer = enquiry_setup
        enquiry_id = await self._create_enquiry(client, auth_headers, business, offer)

        # Customer sends a message
        await client.post(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/messages",
            headers=auth_headers,
            json={"content": "Customer message"},
        )

        # Business sends a message
        await client.post(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/messages",
            headers=second_auth_headers,
            json={"content": "Business reply"},
        )

        # Customer lists messages
        response = await client.get(
            f"/api/v1/enquiries/my-enquiries/{enquiry_id}/messages",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

        # Business lists messages
        response = await client.get(
            f"/api/v1/businesses/{business.id}/enquiries/{enquiry_id}/messages",
            headers=second_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
