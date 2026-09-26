"""Stripe webhook reconciliation & idempotency.

Creates the stripe_events table for tracking processed Stripe webhook
events.  This guarantees idempotent processing — duplicate webhook
deliveries are detected and acknowledged without re-processing.

Also adds dispute-tracking columns to the payments table:
- dispute_id: Stripe dispute/chargeback ID
- dispute_reason: why the dispute was opened
- dispute_evidence: raw Stripe dispute payload
- dispute_created_at: when the dispute was opened in Stripe
- dispute_status: needs_response, under_review, won, lost

Revision ID: 019_stripe_webhook
Revises: 018_commercial_policy
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "019_stripe_webhook"
down_revision: str = "018_commercial_policy"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ── stripe_events table ────────────────────────────────────────
    op.create_table(
        "stripe_events",
        sa.Column("stripe_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payment_intent_id", sa.String(255), nullable=True),
        sa.Column("stripe_account_id", sa.String(255), nullable=True),
        sa.Column("business_id", UUID(as_uuid=True), nullable=True),
        sa.Column("payment_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="processed"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("stripe_created_at", sa.DateTime(timezone=True), nullable=True),
        # Base model columns
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_events_event_id"),
        # Foreign keys
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        # Indexes
        sa.Index("ix_stripe_events_business_id", "business_id"),
        sa.Index("ix_stripe_events_payment_id", "payment_id"),
        sa.Index("ix_stripe_events_payment_intent_id", "payment_intent_id"),
        sa.Index("ix_stripe_events_event_type", "event_type"),
        sa.Index("ix_stripe_events_created_at", "created_at"),
    )

    # ── Dispute tracking columns on payments ───────────────────────
    op.add_column("payments", sa.Column("dispute_id", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("dispute_reason", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("dispute_evidence", JSONB, nullable=True))
    op.add_column(
        "payments",
        sa.Column("dispute_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payments", sa.Column("dispute_status", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "dispute_status")
    op.drop_column("payments", "dispute_created_at")
    op.drop_column("payments", "dispute_evidence")
    op.drop_column("payments", "dispute_reason")
    op.drop_column("payments", "dispute_id")
    op.drop_table("stripe_events")
