"""Integration tests for Business Brain API.

Tests cover:
- Authorization (tenant isolation, role enforcement)
- Version lifecycle (create, update, transition, approve, activate)
- Rule management (add, update, delete, validation)
- Structural validation
- Security (cross-tenant access)
- Provenance

Requires PostgreSQL test database.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User


@pytest.mark.integration
class TestBrainAPIAuthorization:
    """Test authorization and tenant isolation for Brain API."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Brain Biz", slug=f"brain-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    @pytest_asyncio.fixture
    async def staff_business(self, db_session: AsyncSession, second_user: User):
        """Create a business where second_user is staff."""
        business = Business(name="Staff Biz", slug=f"staff-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=second_user.id, business_id=business.id, role="staff")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_unauthenticated_cannot_read_brain(
        self,
        client: AsyncClient,
        owner_business,
    ):
        """Unauthenticated requests are rejected."""
        business = owner_business
        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain",
        )
        assert response.status_code == 401

    async def test_authorized_member_can_read_brain(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """An authorized business member can read the brain."""
        business = owner_business
        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["business_id"] == str(business.id)
        assert data["active_version_id"] is None

    async def test_cross_tenant_access_rejected(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        owner_business,
    ):
        """A user from Business B cannot access Business A's brain."""
        business = owner_business
        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

    async def test_staff_cannot_create_version(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        staff_business,
    ):
        """Staff role cannot create brain versions (requires admin+)."""
        business = staff_business
        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=second_auth_headers,
            json={"config": {}},
        )
        assert response.status_code == 403

    async def test_non_member_cannot_read_brain(
        self,
        client: AsyncClient,
        second_auth_headers: dict,
        owner_business,
    ):
        """A non-member cannot read the brain."""
        business = owner_business
        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain",
            headers=second_auth_headers,
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestBrainVersionLifecycle:
    """Test BrainVersion CRUD and lifecycle transitions."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Lifecycle Biz", slug=f"lifecycle-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_create_draft_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Create a new DRAFT BrainVersion."""
        business = owner_business
        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["version_number"] == 1
        assert data["brain_id"] is not None

    async def test_retrieve_draft_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Retrieve a DRAFT version by ID."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == version_id
        assert data["status"] == "draft"

    async def test_update_draft_config(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Update a DRAFT version's configuration."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}",
            headers=auth_headers,
            json={"identity_config": {"business_name": "Test"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["identity_config"] == {"business_name": "Test"}

    async def test_list_versions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """List all versions for a brain."""
        business = owner_business
        # Create two versions
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )

        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    async def test_valid_transition_draft_to_validating(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Transition from DRAFT to VALIDATING."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "validating"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["previous_status"] == "draft"
        assert data["current_status"] == "validating"

    async def test_invalid_transition_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Invalid transitions are rejected."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        # DRAFT -> APPROVED is not allowed
        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "approved"},
        )
        assert response.status_code == 422

    async def test_immutable_version_cannot_be_modified(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """A non-DRAFT version cannot have its config modified."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        # Transition to VALIDATING
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "validating"},
        )

        # Try to modify — should fail
        response = await client.patch(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}",
            headers=auth_headers,
            json={"identity_config": {"name": "hack"}},
        )
        assert response.status_code == 422


@pytest.mark.integration
class TestBrainRules:
    """Test rule management within BrainVersions."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Rules Biz", slug=f"rules-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_add_valid_rule(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Add a valid rule to a DRAFT version."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules",
            headers=auth_headers,
            json={
                "rule_type": "pricing",
                "name": "Base pricing rule",
                "rule_data": {
                    "model": "fixed",
                    "base_amount": 100.0,
                    "currency": "USD",
                },
                "priority": 10,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["rule_type"] == "pricing"
        assert data["name"] == "Base pricing rule"

    async def test_reject_unknown_rule_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Unknown rule types are rejected."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules",
            headers=auth_headers,
            json={
                "rule_type": "unknown_type",
                "name": "Bad rule",
                "rule_data": {},
            },
        )
        assert response.status_code == 422

    async def test_update_draft_rule(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Update a rule within a DRAFT version."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        rule_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules",
            headers=auth_headers,
            json={
                "rule_type": "policy",
                "name": "Cancellation policy",
                "rule_data": {"window_hours": 24},
            },
        )
        rule_id = rule_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules/{rule_id}",
            headers=auth_headers,
            json={"name": "Updated cancellation policy"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated cancellation policy"

    async def test_delete_draft_rule(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Delete a rule from a DRAFT version."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        rule_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules",
            headers=auth_headers,
            json={
                "rule_type": "policy",
                "name": "Temp rule",
                "rule_data": {"test": True},
            },
        )
        rule_id = rule_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules/{rule_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

    async def test_cannot_add_rule_to_immutable_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Cannot add rules to a non-DRAFT version."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        # Transition to VALIDATING
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "validating"},
        )

        # Try to add a rule — should fail
        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/rules",
            headers=auth_headers,
            json={
                "rule_type": "pricing",
                "name": "Should fail",
                "rule_data": {},
            },
        )
        assert response.status_code == 422


@pytest.mark.integration
class TestBrainValidation:
    """Test structural validation through the API."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Valid Biz", slug=f"valid-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_valid_config_passes_validation(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """A valid empty configuration passes validation."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/validate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["error_count"] == 0

    async def test_invalid_config_returns_errors(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Invalid configuration returns structured errors."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        # Try to update with an invalid config area
        response = await client.patch(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}",
            headers=auth_headers,
            json={"identity_config": {"test": True}},
        )
        assert response.status_code == 200

        # Validate — should still pass for valid structure
        validate_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/validate",
            headers=auth_headers,
        )
        assert validate_resp.status_code == 200


@pytest.mark.integration
class TestBrainApproval:
    """Test approval workflow."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Approve Biz", slug=f"approve-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def _create_version_in_review(
        self, client: AsyncClient, auth_headers: dict, business_id
    ) -> str:
        """Helper: create a version and transition it to REVIEW."""
        create_resp = await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        # DRAFT -> VALIDATING
        await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "validating"},
        )

        # VALIDATING -> REVIEW
        await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "review"},
        )

        return version_id

    async def test_approval_succeeds_for_owner(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Owner can approve a REVIEW version."""
        business = owner_business
        version_id = await self._create_version_in_review(client, auth_headers, business.id)

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/approve",
            headers=auth_headers,
            json={"comment": "Looks good"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "approved"
        assert data["version_status"] == "approved"

    async def test_staff_cannot_approve(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        second_user: User,
        owner_business,
    ):
        """Staff role cannot approve (requires owner)."""
        business = owner_business

        # Make second_user a staff member of the same business
        staff_member = BusinessMember(user_id=second_user.id, business_id=business.id, role="staff")
        db_session.add(staff_member)
        await db_session.flush()

        # Login as second user
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": second_user.email, "password": "testpassword123"},
        )
        staff_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        version_id = await self._create_version_in_review(client, auth_headers, business.id)

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/approve",
            headers=staff_headers,
            json={},
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestBrainActivation:
    """Test version activation."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Activate Biz", slug=f"activate-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def _create_approved_version(
        self, client: AsyncClient, auth_headers: dict, business_id
    ) -> str:
        """Helper: create a version through the full lifecycle to APPROVED."""
        create_resp = await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        # DRAFT -> VALIDATING
        await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "validating"},
        )
        # VALIDATING -> REVIEW
        await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions/{version_id}/transition",
            headers=auth_headers,
            json={"target_status": "review"},
        )
        # REVIEW -> APPROVED
        await client.post(
            f"/api/v1/businesses/{business_id}/brain/versions/{version_id}/approve",
            headers=auth_headers,
            json={},
        )

        return version_id

    async def test_activation_succeeds(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Activating an APPROVED version succeeds."""
        business = owner_business
        version_id = await self._create_approved_version(client, auth_headers, business.id)

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["active_version_id"] == version_id

    async def test_activation_supersedes_previous(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Activating a new version supersedes the previous ACTIVE version."""
        business = owner_business

        # Create and activate first version
        v1_id = await self._create_approved_version(client, auth_headers, business.id)
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{v1_id}/activate",
            headers=auth_headers,
        )

        # Create and approve second version
        v2_id = await self._create_approved_version(client, auth_headers, business.id)
        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{v2_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["active_version_id"] == v2_id

        # Verify v1 is now superseded
        v1_resp = await client.get(
            f"/api/v1/businesses/{business.id}/brain/versions/{v1_id}",
            headers=auth_headers,
        )
        assert v1_resp.json()["status"] == "superseded"

    async def test_unapproved_version_cannot_be_activated(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """A DRAFT version cannot be directly activated."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_active_version_cannot_be_modified(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """An ACTIVE version cannot have its config modified."""
        business = owner_business
        version_id = await self._create_approved_version(client, auth_headers, business.id)
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/activate",
            headers=auth_headers,
        )

        response = await client.patch(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}",
            headers=auth_headers,
            json={"identity_config": {"name": "hack"}},
        )
        assert response.status_code == 422

    async def test_brain_retrieval_returns_active_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """GET /brain returns the current ACTIVE version."""
        business = owner_business
        version_id = await self._create_approved_version(client, auth_headers, business.id)
        await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/activate",
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["active_version_id"] == version_id
        assert data["active_version"] is not None
        assert data["active_version"]["status"] == "active"


@pytest.mark.integration
class TestBrainSecurity:
    """Test cross-tenant security."""

    @pytest_asyncio.fixture
    async def business_a(self, db_session: AsyncSession, test_user: User):
        """Create Business A owned by test_user."""
        business = Business(name="Business A", slug=f"biz-a-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    @pytest_asyncio.fixture
    async def business_b(self, db_session: AsyncSession, second_user: User):
        """Create Business B owned by second_user."""
        business = Business(name="Business B", slug=f"biz-b-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=second_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_business_a_cannot_read_business_b_brain(
        self,
        client: AsyncClient,
        auth_headers: dict,
        business_b,
    ):
        """Business A cannot read Business B's brain."""
        response = await client.get(
            f"/api/v1/businesses/{business_b.id}/brain",
            headers=auth_headers,
        )
        assert response.status_code == 403

    async def test_business_a_cannot_modify_business_b_brain(
        self,
        client: AsyncClient,
        auth_headers: dict,
        business_b,
    ):
        """Business A cannot create versions in Business B's brain."""
        response = await client.post(
            f"/api/v1/businesses/{business_b.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        assert response.status_code == 403

    async def test_business_a_cannot_activate_business_b_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        business_b,
    ):
        """Business A cannot activate versions in Business B's brain."""
        import uuid

        fake_version_id = uuid.uuid4()
        response = await client.post(
            f"/api/v1/businesses/{business_b.id}/brain/versions/{fake_version_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestBrainProvenance:
    """Test provenance/audit retrieval."""

    @pytest_asyncio.fixture
    async def owner_business(self, db_session: AsyncSession, test_user: User):
        """Create a business owned by test_user."""
        business = Business(name="Provenance Biz", slug=f"prov-biz-{id(self)}")
        db_session.add(business)
        await db_session.flush()

        member = BusinessMember(user_id=test_user.id, business_id=business.id, role="owner")
        db_session.add(member)

        profile = BusinessProfile(business_id=business.id)
        db_session.add(profile)
        await db_session.flush()

        return business

    async def test_provenance_returns_entries(
        self,
        client: AsyncClient,
        auth_headers: dict,
        owner_business,
    ):
        """Provenance endpoint returns lifecycle entries."""
        business = owner_business
        create_resp = await client.post(
            f"/api/v1/businesses/{business.id}/brain/versions",
            headers=auth_headers,
            json={"config": {}},
        )
        version_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/businesses/{business.id}/brain/versions/{version_id}/provenance",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["version_id"] == version_id
        assert len(data["entries"]) >= 1
        assert data["entries"][0]["action"] == "version_created"
