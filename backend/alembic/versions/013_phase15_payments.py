"""Phase 15 — Payments & Financial Operations.

Adds:
- payments: payment transactions with idempotency, provider tracking,
  refund tracking, and tenant isolation
- payment_attempts: append-only provider attempt history per payment
- invoices: paid_amount tracking column for fast balance queries

Revision ID: 013_phase15_payments
Revises: 012_phase14b_voice_runtime
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "013_phase15_payments"
down_revision: Union[str, None] = "012_phase14b_voice_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create payments table
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "business_id",
            UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column(
            "payment_method", sa.String(50), nullable=False, server_default="card"
        ),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="pending"
        ),
        sa.Column("provider", sa.String(50), nullable=False, server_default="stub"),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column(
            "refunded_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("refund_provider_reference", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_evidence", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_message", sa.Text, nullable=True),
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
        # Constraints
        sa.UniqueConstraint(
            "idempotency_key", name="uq_payments_idempotency_key"
        ),
    )

    # Indexes for payments
    op.create_index("ix_payments_business_id", "payments", ["business_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index(
        "ix_payments_provider_reference", "payments", ["provider_reference"]
    )

    # 2. Create payment_attempts table
    op.create_table(
        "payment_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "provider", sa.String(50), nullable=False, server_default="stub"
        ),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="pending"
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("provider_response", JSONB, nullable=True),
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

    # Indexes for payment_attempts
    op.create_index(
        "ix_payment_attempts_payment_id",
        "payment_attempts",
        ["payment_id"],
    )
    op.create_index(
        "ix_payment_attempts_provider_reference",
        "payment_attempts",
        ["provider_reference"],
    )


def downgrade() -> None:
    op.drop_table("payment_attempts")
    op.drop_table("payments")
