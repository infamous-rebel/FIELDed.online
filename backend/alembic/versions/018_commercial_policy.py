"""Commercial Policy & fee evidence.

Creates the commercial_policies table for the central FIELDed
commercial policy engine.  Adds fee_evidence JSONB columns to
quotes, invoices, payments, and service_ledger_entries so that
every transaction retains the policy that governed its fee.

Revision ID: 018_commercial_policy
Revises: 017_stripe_connect
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "018_commercial_policy"
down_revision: str | None = "017_stripe_connect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── commercial_policies table ─────────────────────────────────
    op.create_table(
        "commercial_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        # Scope targets
        sa.Column("business_id", UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", UUID(as_uuid=True), nullable=True),
        sa.Column("plan_key", sa.String(100), nullable=True),
        sa.Column("promotion_code", sa.String(100), nullable=True),
        # Fee structure
        sa.Column("fee_type", sa.String(50), nullable=False),
        sa.Column("percentage", sa.Numeric(precision=7, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("fixed_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("fixed_currency", sa.String(3), nullable=False, server_default="GBP"),
        # Time bounds
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        # Lifecycle
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        # Eligibility / disclosure / config
        sa.Column("eligibility", JSONB, nullable=True),
        sa.Column("disclosure", sa.Text, nullable=True),
        sa.Column("config", JSONB, nullable=True),
        # Soft-delete flag
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        # Base model columns
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["service_categories.id"], ondelete="SET NULL"),
        # Constraints
        sa.UniqueConstraint("scope", "name", "version", name="uq_commercial_policy_scope_name_version"),
    )

    # Indexes
    op.create_index("ix_commercial_policies_scope_status", "commercial_policies", ["scope", "status"])
    op.create_index("ix_commercial_policies_business_id", "commercial_policies", ["business_id"])
    op.create_index("ix_commercial_policies_category_id", "commercial_policies", ["category_id"])
    op.create_index(
        "ix_commercial_policies_effective", "commercial_policies", ["effective_from", "effective_until"]
    )
    op.create_index("ix_commercial_policies_promotion_code", "commercial_policies", ["promotion_code"])

    # ── fee_evidence columns on existing financial tables ─────────
    op.add_column("quotes", sa.Column("fee_evidence", JSONB, nullable=True))
    op.add_column("invoices", sa.Column("fee_evidence", JSONB, nullable=True))
    op.add_column("payments", sa.Column("fee_evidence", JSONB, nullable=True))
    op.add_column("service_ledger_entries", sa.Column("fee_evidence", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("service_ledger_entries", "fee_evidence")
    op.drop_column("payments", "fee_evidence")
    op.drop_column("invoices", "fee_evidence")
    op.drop_column("quotes", "fee_evidence")

    op.drop_index("ix_commercial_policies_promotion_code", table_name="commercial_policies")
    op.drop_index("ix_commercial_policies_effective", table_name="commercial_policies")
    op.drop_index("ix_commercial_policies_category_id", table_name="commercial_policies")
    op.drop_index("ix_commercial_policies_business_id", table_name="commercial_policies")
    op.drop_index("ix_commercial_policies_scope_status", table_name="commercial_policies")

    op.drop_table("commercial_policies")
