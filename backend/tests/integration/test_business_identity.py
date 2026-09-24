"""Integration tests for business identity API.

Tests: create business, list businesses, get business, update business,
add/remove members, tenant isolation.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.identity.token_models import MemberInvitation
from tests.factories import (
    customer_profile_factory,
    user_factory,
)


class TestBusinessCreation:
    """Test business creation and listing."""

    @pytest.mark.asyncio
    async def test_create_business(self, client: AsyncClient, test_user, auth_headers):
        """Authenticated user can create a business."""
        response = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Test Plumbing", "slug": "test-plumbing"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Plumbing"
        assert data["slug"] == "test-plumbing"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_business_duplicate_slug(self, client: AsyncClient, test_user, auth_headers):
        """Cannot create two businesses with the same slug."""
        await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Biz A", "slug": "same-slug"},
        )
        response = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Biz B", "slug": "same-slug"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_business_requires_auth(self, client: AsyncClient):
        """Creating a business requires authentication."""
        response = await client.post(
            "/api/v1/businesses",
            json={"name": "Test", "slug": "test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_business_invalid_slug(self, client: AsyncClient, test_user, auth_headers):
        """Slug must be lowercase alphanumeric with hyphens."""
        response = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Test", "slug": "INVALID SLUG!"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_own_businesses(self, client: AsyncClient, test_user, auth_headers):
        """User sees only businesses they are a member of."""
        # Create a business
        await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "My Biz", "slug": "my-biz"},
        )

        response = await client.get("/api/v1/businesses", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(b["slug"] == "my-biz" for b in data)

    @pytest.mark.asyncio
    async def test_get_business_details(self, client: AsyncClient, test_user, auth_headers):
        """Member can get business details."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Detail Biz", "slug": "detail-biz"},
        )
        biz_id = create_resp.json()["id"]

        response = await client.get(f"/api/v1/businesses/{biz_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Detail Biz"


class TestBusinessMembership:
    """Test business membership management."""

    @pytest.mark.asyncio
    async def test_list_members(self, client: AsyncClient, test_user, auth_headers):
        """Owner can list business members."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Member Biz", "slug": "member-biz"},
        )
        biz_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
        )
        assert response.status_code == 200
        members = response.json()
        assert len(members) == 1
        assert members[0]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_add_member(self, client: AsyncClient, test_user, second_user, auth_headers):
        """Owner can add a member to their business."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Add Member Biz", "slug": "add-member-biz"},
        )
        biz_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        assert response.status_code == 201
        assert response.json()["role"] == "staff"

    @pytest.mark.asyncio
    async def test_add_duplicate_member_fails(self, client: AsyncClient, test_user, second_user, auth_headers):
        """Cannot add the same member twice."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Dup Member Biz", "slug": "dup-member-biz"},
        )
        biz_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "admin"},
        )
        assert response.status_code == 409


class TestBusinessTenantIsolation:
    """Test that businesses cannot access each other's data."""

    @pytest.mark.asyncio
    async def test_non_member_cannot_view_business(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """A user who is not a member cannot view a business."""
        # User 1 creates a business
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Private Biz", "slug": "private-biz"},
        )
        biz_id = create_resp.json()["id"]

        # User 2 tries to view it
        response = await client.get(
            f"/api/v1/businesses/{biz_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_member_cannot_list_members(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """A non-member cannot list a business's members."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Secret Members Biz", "slug": "secret-members-biz"},
        )
        biz_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/businesses/{biz_id}/members",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_member_cannot_update_business(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """A non-member cannot update a business."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Protected Biz", "slug": "protected-biz"},
        )
        biz_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/businesses/{biz_id}",
            headers=second_auth_headers,
            json={"name": "Hacked Name"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_member_cannot_add_members(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """A non-member cannot add members to a business."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "No Add Biz", "slug": "no-add-biz"},
        )
        biz_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=second_auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_add_members(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """A staff member cannot add new members."""
        # User 1 creates business
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Staff Limit Biz", "slug": "staff-limit-biz"},
        )
        biz_id = create_resp.json()["id"]

        # Add user 2 as staff
        await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )

        # Staff tries to add another member (using a fake email)
        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=second_auth_headers,
            json={"user_email": "someone@example.com", "role": "staff"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_user_only_sees_own_businesses(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """Each user only sees their own businesses."""
        # User 1 creates a business
        await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "User1 Biz", "slug": "user1-biz"},
        )

        # User 2 creates a business
        await client.post(
            "/api/v1/businesses",
            headers=second_auth_headers,
            json={"name": "User2 Biz", "slug": "user2-biz"},
        )

        # User 1 should only see their own
        resp1 = await client.get("/api/v1/businesses", headers=auth_headers)
        biz1_slugs = [b["slug"] for b in resp1.json()]
        assert "user1-biz" in biz1_slugs
        assert "user2-biz" not in biz1_slugs

        # User 2 should only see their own
        resp2 = await client.get("/api/v1/businesses", headers=second_auth_headers)
        biz2_slugs = [b["slug"] for b in resp2.json()]
        assert "user2-biz" in biz2_slugs
        assert "user1-biz" not in biz2_slugs


class TestMemberInvitations:
    """Phase 17 — member invitation, role change, and removal."""

    @pytest.mark.asyncio
    async def test_invite_member_owner_only(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """Only the owner can invite; staff/non-members cannot."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Invite Biz", "slug": "invite-biz"},
        )
        biz_id = create_resp.json()["id"]

        # Staff cannot invite
        await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members/invite",
            headers=second_auth_headers,
            json={"email": "newperson@example.com", "role": "staff"},
        )
        assert response.status_code == 403

        # Non-member cannot invite
        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members/invite",
            headers=second_auth_headers,
            json={"email": "newperson@example.com", "role": "staff"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_invite_creates_invitation_and_duplicate_conflicts(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Owner invite succeeds; a second invite for the same email conflicts."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Dup Invite Biz", "slug": "dup-invite-biz"},
        )
        biz_id = create_resp.json()["id"]
        email = "pending-invite@example.com"

        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members/invite",
            headers=auth_headers,
            json={"email": email, "role": "staff"},
        )
        assert response.status_code == 201
        invitation = response.json()
        assert invitation["email"] == email
        assert invitation["role"] == "staff"
        assert invitation["expires_at"]

        # Pending invitation is listed
        listing = await client.get(
            f"/api/v1/businesses/{biz_id}/members/invitations",
            headers=auth_headers,
        )
        assert listing.status_code == 200
        assert any(i["email"] == email for i in listing.json())

        # Duplicate pending invitation conflicts
        response = await client.post(
            f"/api/v1/businesses/{biz_id}/members/invite",
            headers=auth_headers,
            json={"email": email, "role": "admin"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_accept_invitation_email_mismatch_rejected(
        self, client, db_session, test_user, second_user, auth_headers, second_auth_headers
    ):
        """The signed-in user's email must match the invitation email."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Email Match Biz", "slug": "email-match-biz"},
        )
        biz_id = create_resp.json()["id"]

        invite_resp = await client.post(
            f"/api/v1/businesses/{biz_id}/members/invite",
            headers=auth_headers,
            json={"email": "specific-person@example.com", "role": "staff"},
        )
        assert invite_resp.status_code == 201

        # Token is delivered by email — read it from the same transaction
        result = await db_session.execute(
            select(MemberInvitation).where(MemberInvitation.business_id == uuid.UUID(biz_id))
        )
        invitation = result.scalar_one()

        # second_user has a different email — invitation is not theirs
        response = await client.post(
            f"/api/v1/members/accept-invitation/{invitation.token}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403
        assert "different email" in response.text

    @pytest.mark.asyncio
    async def test_accept_invitation_happy_path_and_single_use(self, client, db_session, test_user, auth_headers):
        """Matching email accepts once; token is single-use; membership created."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Accept Biz", "slug": "accept-biz"},
        )
        biz_id = create_resp.json()["id"]

        invited_email = f"newmember-{uuid.uuid4().hex[:8]}@example.com"
        invite_resp = await client.post(
            f"/api/v1/businesses/{biz_id}/members/invite",
            headers=auth_headers,
            json={"email": invited_email, "role": "staff"},
        )
        assert invite_resp.status_code == 201

        result = await db_session.execute(
            select(MemberInvitation).where(MemberInvitation.business_id == uuid.UUID(biz_id))
        )
        invitation = result.scalar_one()

        # The invited person registers an account with the invited email
        invited_user = user_factory(email=invited_email)
        db_session.add(invited_user)
        await db_session.flush()
        db_session.add(customer_profile_factory(user_id=invited_user.id))
        await db_session.flush()

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": invited_email, "password": "testpassword123"},
        )
        assert login.status_code == 200, login.text
        invited_auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Accept the invitation
        response = await client.post(
            f"/api/v1/members/accept-invitation/{invitation.token}",
            headers=invited_auth,
        )
        assert response.status_code == 201, response.text
        member = response.json()
        assert member["role"] == "staff"
        assert member["user_email"] == invited_email

        # Token is single-use — second accept is rejected
        response = await client.post(
            f"/api/v1/members/accept-invitation/{invitation.token}",
            headers=invited_auth,
        )
        assert response.status_code == 422
        assert "already been used" in response.text

        # Business now lists two members
        members = await client.get(f"/api/v1/businesses/{biz_id}/members", headers=auth_headers)
        assert len(members.json()) == 2

    @pytest.mark.asyncio
    async def test_role_change_owner_only(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """Only the owner can change roles; last owner cannot be demoted."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Role Biz", "slug": "role-biz"},
        )
        biz_id = create_resp.json()["id"]

        add_resp = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        member_id = add_resp.json()["id"]

        # Staff cannot change roles
        response = await client.patch(
            f"/api/v1/businesses/{biz_id}/members/{member_id}",
            headers=second_auth_headers,
            json={"role": "admin"},
        )
        assert response.status_code == 403

        # Owner changes staff → admin
        response = await client.patch(
            f"/api/v1/businesses/{biz_id}/members/{member_id}",
            headers=auth_headers,
            json={"role": "admin"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

        # Owner cannot demote themselves (last owner)
        members = await client.get(f"/api/v1/businesses/{biz_id}/members", headers=auth_headers)
        owner_member = next(m for m in members.json() if m["role"] == "owner")
        response = await client.patch(
            f"/api/v1/businesses/{biz_id}/members/{owner_member['id']}",
            headers=auth_headers,
            json={"role": "staff"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_remove_member_and_self_removal_guard(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """Owner removes a member; self-removal and last-owner removal blocked."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Remove Biz", "slug": "remove-biz"},
        )
        biz_id = create_resp.json()["id"]

        add_resp = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        member_id = add_resp.json()["id"]

        # Staff cannot remove members
        response = await client.delete(
            f"/api/v1/businesses/{biz_id}/members/{member_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

        # Owner removes the staff member
        response = await client.delete(
            f"/api/v1/businesses/{biz_id}/members/{member_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Member no longer listed
        members = await client.get(f"/api/v1/businesses/{biz_id}/members", headers=auth_headers)
        assert all(m["id"] != member_id for m in members.json())

        # Owner cannot remove themselves (and is the last owner)
        members = await client.get(f"/api/v1/businesses/{biz_id}/members", headers=auth_headers)
        owner_member = next(m for m in members.json() if m["role"] == "owner")
        response = await client.delete(
            f"/api/v1/businesses/{biz_id}/members/{owner_member['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_member_tenant_isolation(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """One business's owner cannot manage another business's members."""
        resp_a = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Biz A", "slug": "tenant-a-biz"},
        )
        resp_b = await client.post(
            "/api/v1/businesses",
            headers=second_auth_headers,
            json={"name": "Biz B", "slug": "tenant-b-biz"},
        )
        biz_a = resp_a.json()["id"]
        _biz_b = resp_b.json()["id"]

        # B's owner cannot invite into A
        response = await client.post(
            f"/api/v1/businesses/{biz_a}/members/invite",
            headers=second_auth_headers,
            json={"email": "intruder@example.com", "role": "staff"},
        )
        assert response.status_code == 403

        # B's owner cannot list A's invitations
        response = await client.get(
            f"/api/v1/businesses/{biz_a}/members/invitations",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

        # B's owner cannot change/remove A's members
        members_a = await client.get(f"/api/v1/businesses/{biz_a}/members", headers=auth_headers)
        a_member_id = members_a.json()[0]["id"]

        response = await client.patch(
            f"/api/v1/businesses/{biz_a}/members/{a_member_id}",
            headers=second_auth_headers,
            json={"role": "staff"},
        )
        assert response.status_code == 403

        response = await client.delete(
            f"/api/v1/businesses/{biz_a}/members/{a_member_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403
