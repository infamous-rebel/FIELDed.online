"""Agent capability & delegation architecture.

Creates the shared agent authorization tables:
- agent_capabilities: per-business, per-agent-type capability grants
- agent_delegations: explicit owner delegation of capabilities
- agent_execution_logs: audit trail of all agent actions

This is the foundational authorization model for all agents:
Discovery, Business Brain/Co-Brain, Call Agent, Marketing Agent.

Revision ID: 020_agent_capabilities
Revises: 019_stripe_webhook
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "020_agent_capabilities"
down_revision: str = "019_stripe_webhook"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ── agent_capabilities ─────────────────────────────────────────
    op.create_table(
        "agent_capabilities",
        sa.Column("business_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("capability_type", sa.String(100), nullable=False),
        sa.Column("authority_mode", sa.String(50), nullable=False, server_default="disabled"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("policy_constraints", JSONB, nullable=True),
        # Base model columns
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.UniqueConstraint(
            "business_id", "agent_type", "capability_type",
            name="uq_agent_capabilities_scope",
        ),
        # Foreign keys
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        # Indexes
        sa.Index("ix_agent_capabilities_business_id", "business_id"),
        sa.Index("ix_agent_capabilities_agent_type", "agent_type"),
        sa.Index("ix_agent_capabilities_is_active", "is_active"),
    )

    # ── agent_delegations ──────────────────────────────────────────
    op.create_table(
        "agent_delegations",
        sa.Column("capability_id", UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("capability_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("granted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        # Base model columns
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(["capability_id"], ["agent_capabilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        # Indexes
        sa.Index("ix_agent_delegations_business_id", "business_id"),
        sa.Index("ix_agent_delegations_capability_id", "capability_id"),
        sa.Index("ix_agent_delegations_status", "status"),
        sa.Index("ix_agent_delegations_agent_type", "agent_type"),
    )

    # ── agent_execution_logs ───────────────────────────────────────
    op.create_table(
        "agent_execution_logs",
        sa.Column("business_id", UUID(as_uuid=True), nullable=False),
        sa.Column("delegation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("capability_type", sa.String(100), nullable=False),
        sa.Column("authority_mode", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_input", JSONB, nullable=True),
        sa.Column("action_output", JSONB, nullable=True),
        sa.Column("validation_passed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("validation_details", JSONB, nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("evidence", JSONB, nullable=True),
        sa.Column("correlation_id", sa.String(255), nullable=True),
        sa.Column("related_enquiry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("related_booking_id", UUID(as_uuid=True), nullable=True),
        # Base model columns
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delegation_id"], ["agent_delegations.id"], ondelete="SET NULL"),
        # Indexes
        sa.Index("ix_agent_execution_logs_business_id", "business_id"),
        sa.Index("ix_agent_execution_logs_delegation_id", "delegation_id"),
        sa.Index("ix_agent_execution_logs_agent_type", "agent_type"),
        sa.Index("ix_agent_execution_logs_action_type", "action_type"),
        sa.Index("ix_agent_execution_logs_correlation_id", "correlation_id"),
        sa.Index("ix_agent_execution_logs_created_at", "created_at"),
    )


def downgrade() -> None:
    op.drop_table("agent_execution_logs")
    op.drop_table("agent_delegations")
    op.drop_table("agent_capabilities")
