"""Google Calendar booking integration.

Creates tables for per-business Google Calendar OAuth connections
and per-booking calendar synchronisation records.

- calendar_connections: one active OAuth connection per business
- calendar_event_sync_records: per-booking sync audit trail with
  deterministic booking-derived event IDs for idempotent creation

Revision ID: 021_calendar_connections
Revises: 020_agent_capabilities
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "021_calendar_connections"
down_revision: str = "020_agent_capabilities"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ── calendar_connections ───────────────────────────────────────
    op.create_table(
        "calendar_connections",
        sa.Column("business_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="google"),
        sa.Column("calendar_id", sa.String(255), nullable=False, server_default="primary"),
        sa.Column("calendar_summary", sa.String(255), nullable=True),
        # Encrypted OAuth tokens (Fernet-encrypted at rest)
        sa.Column("access_token_encrypted", sa.Text, nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text, nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        # Google account metadata (non-secret)
        sa.Column("google_email", sa.String(320), nullable=True),
        # Lifecycle
        sa.Column("status", sa.String(50), nullable=False, server_default="connecting"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        # Base model columns
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.UniqueConstraint("business_id", name="uq_calendar_connections_business_id"),
        # Foreign keys
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        # Indexes
        sa.Index("ix_calconn_business_id", "business_id"),
        sa.Index("ix_calconn_status", "status"),
    )

    # ── calendar_event_sync_records ──────────────────────────────
    op.create_table(
        "calendar_event_sync_records",
        sa.Column("business_id", UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", UUID(as_uuid=True), nullable=False),
        # Deterministic FIELDed booking-derived event identifier
        sa.Column("booking_event_id", sa.String(255), nullable=False),
        # Google Calendar event ID (from provider after first sync)
        sa.Column("calendar_event_id", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="google"),
        sa.Column("calendar_id", sa.String(255), nullable=False, server_default="primary"),
        # Sync lifecycle
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("sync_evidence", JSONB, nullable=True),
        # Base model columns
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.UniqueConstraint("booking_event_id", name="uq_calendar_sync_booking_event_id"),
        # Foreign keys
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        # Indexes
        sa.Index("ix_calsync_business_id", "business_id"),
        sa.Index("ix_calsync_booking_id", "booking_id"),
        sa.Index("ix_calsync_status", "status"),
    )


def downgrade() -> None:
    op.drop_table("calendar_event_sync_records")
    op.drop_table("calendar_connections")
