"""Phase 13 — Service Execution, Invoice, Ledger.

Creates:
- service_executions: tracks actual service delivery
- invoices: financial invoices for completed services
- invoice_line_items: line items within invoices
- service_ledger_entries: operational service ledger

Revision ID: 009_phase13_service_execution_invoice_ledger
Revises: 008_currency_columns
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "009_phase13_service_execution_invoice_ledger"
down_revision: Union[str, None] = "008_currency_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Service Executions ──
    op.create_table(
        "service_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("service_offer_id", UUID(as_uuid=True), sa.ForeignKey("service_offers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quote_id", UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="scheduled"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completion_evidence", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_service_executions_business_id", "service_executions", ["business_id"])
    op.create_index("ix_service_executions_customer_id", "service_executions", ["customer_id"])
    op.create_index("ix_service_executions_booking_id", "service_executions", ["booking_id"])
    op.create_index("ix_service_executions_status", "service_executions", ["status"])

    # ── Invoices ──
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_execution_id", UUID(as_uuid=True), sa.ForeignKey("service_executions.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quote_id", UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_number", sa.String(50), nullable=False),
        sa.Column("issue_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("tax", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("payment_status", sa.String(50), nullable=False, server_default="unpaid"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("business_id", "invoice_number", name="uq_invoice_business_number"),
    )
    op.create_index("ix_invoices_business_id", "invoices", ["business_id"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_service_execution_id", "invoices", ["service_execution_id"])
    op.create_index("ix_invoices_booking_id", "invoices", ["booking_id"])
    op.create_index("ix_invoices_payment_status", "invoices", ["payment_status"])

    # ── Invoice Line Items ──
    op.create_table(
        "invoice_line_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("service_reference", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False, server_default="1.00"),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("tax", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invoice_line_items_invoice_id", "invoice_line_items", ["invoice_id"])

    # ── Service Ledger Entries ──
    op.create_table(
        "service_ledger_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_execution_id", UUID(as_uuid=True), sa.ForeignKey("service_executions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quote_id", UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_offer_id", UUID(as_uuid=True), sa.ForeignKey("service_offers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("completion_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gross_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("tax", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("net_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("payment_status", sa.String(50), nullable=False, server_default="unpaid"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("adjusts_entry_id", UUID(as_uuid=True), sa.ForeignKey("service_ledger_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transaction_reference", sa.String(100), nullable=True, unique=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ledger_entries_business_id", "service_ledger_entries", ["business_id"])
    op.create_index("ix_ledger_entries_customer_id", "service_ledger_entries", ["customer_id"])
    op.create_index("ix_ledger_entries_completion_date", "service_ledger_entries", ["completion_date"])
    op.create_index("ix_ledger_entries_payment_status", "service_ledger_entries", ["payment_status"])

    # Partial unique index: one primary entry per service execution
    op.create_index(
        "uq_ledger_primary_execution",
        "service_ledger_entries",
        ["service_execution_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("service_ledger_entries")
    op.drop_table("invoice_line_items")
    op.drop_table("invoices")
    op.drop_table("service_executions")
