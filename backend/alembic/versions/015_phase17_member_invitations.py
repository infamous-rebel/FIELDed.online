"""Phase 17 — Member invitations.

Adds:
- member_invitations: pending invitations for people (who may not yet be
  on FIELDed) to join a business with a specific role. Single-use token,
  same lifecycle pattern as password_reset_tokens.

Revision ID: 015_phase17_member_invitations
Revises: 014_phase17_reviews
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "015_phase17_member_invitations"
down_revision: Union[str, None] = "014_phase17_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "member_invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role", sa.String(50), nullable=False, server_default="staff"
        ),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column(
            "invited_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes
    op.create_index(
        "ix_member_invitations_business_id", "member_invitations", ["business_id"]
    )
    op.create_index("ix_member_invitations_email", "member_invitations", ["email"])
    op.create_index(
        "ix_member_invitations_token",
        "member_invitations",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("member_invitations")
