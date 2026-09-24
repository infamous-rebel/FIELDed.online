"""Security tests for authorization and privilege escalation.

Tests that users cannot escalate their privileges or access
resources beyond their authorization level.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from httpx import AsyncClient


class TestPrivilegeEscalation:
    """Test that privilege escalation is prevented."""

    @pytest.mark.asyncio
    async def test_staff_cannot_update_business(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """Staff member cannot update business details."""
        # User 1 creates business and adds user 2 as staff
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Staff Test Biz", "slug": "staff-test-biz"},
        )
        biz_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )

        # Staff tries to update
        response = await client.put(
            f"/api/v1/businesses/{biz_id}",
            headers=second_auth_headers,
            json={"name": "Hacked"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_remove_members(
        self, client: AsyncClient, test_user, second_user, auth_headers, second_auth_headers
    ):
        """Staff member cannot remove other members."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Staff Remove Biz", "slug": "staff-remove-biz"},
        )
        biz_id = create_resp.json()["id"]

        # Add user 2 as staff
        add_resp = await client.post(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
            json={"user_email": second_user.email, "role": "staff"},
        )
        member_id = add_resp.json()["id"]

        # Staff tries to remove a member
        response = await client.delete(
            f"/api/v1/businesses/{biz_id}/members/{member_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_remove_self(self, client: AsyncClient, test_user, auth_headers):
        """Owner cannot remove themselves from a business."""
        create_resp = await client.post(
            "/api/v1/businesses",
            headers=auth_headers,
            json={"name": "Self Remove Biz", "slug": "self-remove-biz"},
        )
        biz_id = create_resp.json()["id"]

        # Get own member ID
        members_resp = await client.get(
            f"/api/v1/businesses/{biz_id}/members",
            headers=auth_headers,
        )
        owner_member_id = members_resp.json()[0]["id"]

        # Try to remove self
        response = await client.delete(
            f"/api/v1/businesses/{biz_id}/members/{owner_member_id}",
            headers=auth_headers,
        )
        assert response.status_code == 409


class TestSessionSecurity:
    """Test session and token security."""

    @pytest.mark.asyncio
    async def test_logout_invalidates_refresh_token(self, client: AsyncClient, test_user, auth_headers):
        """After logout, the refresh token is revoked."""
        # Login to get tokens
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        tokens = login_resp.json()

        # Logout with refresh token
        logout_resp = await client.post(
            "/api/v1/auth/logout",
            headers=auth_headers,
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert logout_resp.status_code == 200

        # Try to use the revoked refresh token
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_rotation(self, client: AsyncClient, test_user):
        """Refresh token rotation: old refresh token is revoked after use."""
        # Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        old_refresh = login_resp.json()["refresh_token"]

        # Use refresh token
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert refresh_resp.status_code == 200
        new_refresh = refresh_resp.json()["refresh_token"]

        # Old refresh token should be revoked
        old_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert old_resp.status_code == 401

        # New refresh token should work
        new_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh},
        )
        assert new_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_deactivated_user_cannot_login(self, client: AsyncClient, db_session, test_user):
        """A deactivated user cannot login."""
        test_user.is_active = False
        await db_session.flush()

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        assert response.status_code == 401


class TestEmailVerification:
    """Test email verification flow."""

    @pytest.mark.asyncio
    async def test_verify_email_with_valid_token(self, client: AsyncClient, db_session):
        """Email verification with a valid token succeeds."""
        # Register a new user
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "verify-test@example.com",
                "password": "securepass123",
                "first_name": "Verify",
                "last_name": "Test",
            },
        )
        assert reg_resp.status_code == 201
        assert reg_resp.json()["is_verified"] is False

        # Get the verification token from the database
        from sqlalchemy import select

        from app.domain.identity.token_models import EmailVerification

        result = await db_session.execute(
            select(EmailVerification).where(EmailVerification.user_id == reg_resp.json()["id"])
        )
        verification = result.scalar_one()

        # Verify email
        verify_resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": verification.token},
        )
        assert verify_resp.status_code == 200

        # Login and check is_verified
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "verify-test@example.com", "password": "securepass123"},
        )
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login_resp.json()['access_token']}"},
        )
        assert me_resp.json()["is_verified"] is True

    @pytest.mark.asyncio
    async def test_verify_email_with_invalid_token(self, client: AsyncClient):
        """Invalid verification token is rejected."""
        response = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": "invalid-token"},
        )
        assert response.status_code == 422


class TestPasswordRecovery:
    """Test password recovery flow."""

    @pytest.mark.asyncio
    async def test_forgot_password_always_returns_success(self, client: AsyncClient, test_user):
        """Forgot password returns success regardless of email existence."""
        # Existing user
        resp1 = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_user.email},
        )
        assert resp1.status_code == 200

        # Non-existing user (same response to prevent enumeration)
        resp2 = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_with_valid_token(self, client: AsyncClient, db_session, test_user):
        """Password reset with valid token succeeds."""
        # Create a reset token
        from datetime import datetime, timedelta

        from app.domain.identity.token_models import PasswordResetToken

        reset_token = PasswordResetToken(
            user_id=test_user.id,
            token="test-reset-token-123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(reset_token)
        await db_session.flush()

        # Reset password
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "test-reset-token-123", "new_password": "newpassword123"},
        )
        assert response.status_code == 200

        # Login with new password
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "newpassword123"},
        )
        assert login_resp.status_code == 200

        # Old password should fail
        old_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "testpassword123"},
        )
        assert old_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_password_with_invalid_token(self, client: AsyncClient):
        """Invalid reset token is rejected."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "new_password": "newpassword123"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_password_single_use(self, client: AsyncClient, db_session, test_user):
        """Reset token can only be used once."""
        from datetime import datetime, timedelta

        from app.domain.identity.token_models import PasswordResetToken

        reset_token = PasswordResetToken(
            user_id=test_user.id,
            token="single-use-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(reset_token)
        await db_session.flush()

        # First use succeeds
        resp1 = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "single-use-token", "new_password": "first-reset-123"},
        )
        assert resp1.status_code == 200

        # Second use fails
        resp2 = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "single-use-token", "new_password": "second-reset-123"},
        )
        assert resp2.status_code == 422
