"""Phase 18 — Business Brain Interactive Co-Brain.

Adds:
- brain_conversations: conversational sessions between Brain and owner
- brain_messages: individual messages within conversations
- brain_proposals: AI-generated proposals for governed business knowledge

This implements the Interactive Co-Brain layer where the Brain learns
about the business through conversation and proposes structured knowledge
that requires explicit owner approval before becoming governed state.

Revision ID: 016_phase18_brain_conversation
Revises: 015_phase17_member_invitations
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "016_phase18_brain_conversation"
down_revision: Union[str, None] = "015_phase17_member_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Brain Conversations
    op.create_table(
        "brain_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_brains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="active",
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("context_summary", sa.Text, nullable=True),
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

    # Indexes for conversations
    op.create_index(
        "ix_brain_conversations_brain_id", "brain_conversations", ["brain_id"]
    )
    op.create_index(
        "ix_brain_conversations_business_id", "brain_conversations", ["business_id"]
    )
    op.create_index(
        "ix_brain_conversations_status", "brain_conversations", ["status"]
    )

    # Brain Messages
    op.create_table(
        "brain_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brain_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
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

    # Indexes for messages
    op.create_index(
        "ix_brain_messages_conversation_id", "brain_messages", ["conversation_id"]
    )
    op.create_index("ix_brain_messages_role", "brain_messages", ["role"])

    # Brain Proposals
    op.create_table(
        "brain_proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_brains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brain_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "business_id",
            UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "proposal_type",
            sa.String(50),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "confidence",
            sa.Float,
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("reasoning_summary", sa.Text, nullable=True),
        sa.Column("proposed_change", JSONB, nullable=False, server_default="{}"),
        sa.Column("affected_area", sa.String(50), nullable=True),
        sa.Column(
            "source_message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brain_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_urgent",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
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

    # Indexes for proposals
    op.create_index("ix_brain_proposals_brain_id", "brain_proposals", ["brain_id"])
    op.create_index(
        "ix_brain_proposals_business_id", "brain_proposals", ["business_id"]
    )
    op.create_index("ix_brain_proposals_status", "brain_proposals", ["status"])
    op.create_index(
        "ix_brain_proposals_conversation_id", "brain_proposals", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_table("brain_proposals")
    op.drop_table("brain_messages")
    op.drop_table("brain_conversations")
