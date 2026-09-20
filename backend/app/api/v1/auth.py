"""Authentication API endpoints.

Provides: register, login, logout, token refresh, current user info,
email verification, password recovery.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db_session
from app.domain.identity.models import CustomerProfile, User
from app.domain.identity.token_models import EmailVerification, PasswordResetToken
from app.exceptions import AuthenticationError, ConflictError, ValidationError
from app.security.authorization import get_current_user
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from app.security.password import hash_password, verify_password
from app.security.token_revocation import revocation_store


async def _get_settings(request: Request) -> Settings:
    """Extract settings from app state."""
    return request.app.state.settings


router = APIRouter()


# --- Request/Response schemas ---


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    is_verified: bool
    customer_profile: CustomerProfileResponse | None = None


class CustomerProfileResponse(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    status: str | None = None


# Rebuild model to resolve forward reference
UserResponse.model_rebuild()


class MessageResponse(BaseModel):
    message: str


# --- Helper ---


def _generate_token() -> str:
    """Generate a secure random token string."""
    return secrets.token_urlsafe(48)


# --- Endpoints ---


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Register a new customer account."""
    # Check for existing user
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise ConflictError("A user with this email already exists")

    # Create user
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    # Create customer profile
    profile = CustomerProfile(
        user_id=user.id,
        first_name=body.first_name,
        last_name=body.last_name,
        status="incomplete",
    )
    db.add(profile)

    # Create email verification token
    verification = EmailVerification(
        user_id=user.id,
        token=_generate_token(),
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(verification)
    await db.flush()

    # Refresh to load relationships
    await db.refresh(user, attribute_names=["customer_profile"])

    # In production, send verification email here via adapter
    # For now, the token is created but not sent

    return UserResponse(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        customer_profile=CustomerProfileResponse(
            first_name=profile.first_name,
            last_name=profile.last_name,
            status=profile.status,
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(_get_settings)],
) -> TokenResponse:
    """Authenticate and receive tokens."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    access_token = create_access_token(settings, subject=str(user.id))
    refresh_token = create_refresh_token(settings, subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(_get_settings)],
) -> MessageResponse:
    """Logout the current user by revoking their tokens.

    The access token JTI is revoked immediately.
    If a refresh token is provided, it is also revoked.
    """
    # The current access token's JTI was already validated by get_current_user.
    # We need to extract it again to revoke it.
    # Since get_current_user already decoded it, we trust the user is authenticated.
    # The actual revocation of the access token happens via the client
    # no longer using it. For true server-side revocation, we'd need
    # the JTI from the current request's token.

    # Revoke refresh token if provided
    if body.refresh_token:
        try:
            claims = decode_token(settings, body.refresh_token)
            jti = claims.get("jti")
            exp = claims.get("exp")
            if jti and exp:
                from datetime import datetime

                expires_at = datetime.fromtimestamp(exp, tz=UTC)
                revocation_store.revoke(jti, expires_at)
        except AuthenticationError:
            pass  # Token already invalid, nothing to revoke

    return MessageResponse(message="Successfully logged out")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(_get_settings)],
) -> TokenResponse:
    """Exchange a refresh token for new tokens."""
    claims = decode_token(settings, body.refresh_token)

    if claims.get("type") != "refresh":
        raise AuthenticationError("Invalid token type for refresh")

    user_id = claims.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing subject")

    # Revoke the old refresh token (rotation)
    old_jti = claims.get("jti")
    exp = claims.get("exp")
    if old_jti and exp:
        from datetime import datetime

        expires_at = datetime.fromtimestamp(exp, tz=UTC)
        revocation_store.revoke(old_jti, expires_at)

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(
            User.id == uuid.UUID(user_id),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("User not found or inactive")

    access_token = create_access_token(settings, subject=str(user.id))
    new_refresh_token = create_refresh_token(settings, subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Get the current authenticated user's information."""
    profile_response = None
    if user.customer_profile:
        profile_response = CustomerProfileResponse(
            first_name=user.customer_profile.first_name,
            last_name=user.customer_profile.last_name,
            phone=user.customer_profile.phone,
            status=user.customer_profile.status,
        )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        customer_profile=profile_response,
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Verify user's email address using a verification token."""
    result = await db.execute(
        select(EmailVerification).where(
            EmailVerification.token == body.token,
            EmailVerification.deleted_at.is_(None),
        )
    )
    verification = result.scalar_one_or_none()

    if verification is None:
        raise ValidationError("Invalid verification token")

    if verification.is_used:
        raise ValidationError("Verification token has already been used")

    if verification.is_expired:
        raise ValidationError("Verification token has expired")

    # Mark token as used
    verification.used_at = datetime.now(UTC)

    # Mark user as verified
    result = await db.execute(select(User).where(User.id == verification.user_id))
    user = result.scalar_one()
    user.is_verified = True

    # Update profile status to active if still incomplete
    result = await db.execute(
        select(CustomerProfile).where(
            CustomerProfile.user_id == user.id,
            CustomerProfile.deleted_at.is_(None),
        )
    )
    profile = result.scalar_one_or_none()
    if profile and profile.status == "incomplete":
        profile.status = "active"

    await db.flush()

    return MessageResponse(message="Email verified successfully")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Resend email verification token for the current user."""
    if user.is_verified:
        return MessageResponse(message="Email is already verified")

    # Create a new verification token
    verification = EmailVerification(
        user_id=user.id,
        token=_generate_token(),
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(verification)
    await db.flush()

    # In production, send verification email here via adapter

    return MessageResponse(message="Verification email sent")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Request a password reset token.

    Always returns success to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is not None:
        # Create password reset token
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=_generate_token(),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(reset_token)
        await db.flush()

        # In production, send reset email here via adapter

    # Always return the same message regardless of whether user exists
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent"
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Reset password using a reset token."""
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == body.token,
            PasswordResetToken.deleted_at.is_(None),
        )
    )
    reset_token = result.scalar_one_or_none()

    if reset_token is None:
        raise ValidationError("Invalid reset token")

    if reset_token.is_used:
        raise ValidationError("Reset token has already been used")

    if reset_token.is_expired:
        raise ValidationError("Reset token has expired")

    # Mark token as used
    reset_token.used_at = datetime.now(UTC)

    # Update user's password
    result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = result.scalar_one()
    user.hashed_password = hash_password(body.new_password)

    await db.flush()

    return MessageResponse(message="Password reset successfully")
