"""Booking automation status tracking.

Creates the booking_automation_status table for independently
tracking each downstream operation triggered by booking lifecycle
events (calendar sync, service execution, payment prep).

Each operation is tracked per (booking_id, operation_type) with
its own status, attempt count, and retry scheduling.

Revision ID: 022_booking_automation_status
Revises: 021_calendar_connections
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "022_booking_automation_status"
down_revision: str = "021_calendar_connections"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_automation_status",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Operation type: CALENDAR_SYNC, SERVICE_EXECUTION, PAYMENT_PREP
        sa.Column("operation_type", sa.String(50), nullable=False),
        # Triggering outbox event type (e.g., BOOKING_CONFIRMED)
        sa.Column("triggering_event", sa.String(100), nullable=False),
        # Status: PENDING, SUCCESS, FAILED, NOT_APPLICABLE, EXHAUSTED
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_evidence", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes
    op.create_index("ix_bas_business_id", "booking_automation_status", ["business_id"])
    op.create_index("ix_bas_booking_id", "booking_automation_status", ["booking_id"])
    op.create_index("ix_bas_status", "booking_automation_status", ["status"])
    op.create_index(
        "ix_bas_operation_booking",
        "booking_automation_status",
        ["operation_type", "booking_id"],
        unique=True,
    )
    op.create_index(
        "ix_bas_retry",
        "booking_automation_status",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bas_retry", table_name="booking_automation_status")
    op.drop_index("ix_bas_operation_booking", table_name="booking_automation_status")
    op.drop_index("ix_bas_status", table_name="booking_automation_status")
    op.drop_index("ix_bas_booking_id", table_name="booking_automation_status")
    op.drop_index("ix_bas_business_id", table_name="booking_automation_status")
    op.drop_table("booking_automation_status")
