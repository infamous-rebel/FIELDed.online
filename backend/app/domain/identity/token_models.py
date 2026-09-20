"""Authentication token models.

EmailVerification and PasswordResetToken are short-lived, single-use tokens
for email verification and password recovery flows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.common.base_model import BaseModel


class EmailVerification(BaseModel):
    """Email verification token.

    Created on registration. The user must present the token to verify their email.
    Tokens are single-use and expire after a configurable period.
    """

    __tablename__ = "email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        return now > self.expires_at


class PasswordResetToken(BaseModel):
    """Password reset token.

    Created when a user requests a password reset.
    Tokens are single-use and expire after a configurable period.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        return now > self.expires_at


class MemberInvitation(BaseModel):
    """Pending member invitation (Phase 17).

    Created by a business owner/admin to invite a person (who may not
    yet be on FIELDed) to join the business with a specific role.
    Single-use token, same lifecycle pattern as PasswordResetToken.
    On acceptance, a BusinessMember record is created — no parallel
    membership subsystem.
    """

    __tablename__ = "member_invitations"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="staff")
    token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        return now > self.expires_at
