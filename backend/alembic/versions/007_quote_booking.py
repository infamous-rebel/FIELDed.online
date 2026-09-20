"""Phase 12 — Quote and Booking tables for pricing/booking runtime.

Adds:
- quotes: deterministic pricing decisions with Brain traceability
- bookings: service engagements with Brain availability evaluation

Both tables retain brain_version_id for historical traceability.

Revision ID: 007_quote_booking
Revises: 006_brain_version_active_unique
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "007_quote_booking"
down_revision: Union[str, None] = "006_brain_version_active_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- quotes ---
    op.create_table(
        "quotes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "customer_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "business_id", UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enquiry_id", UUID(as_uuid=True),
            sa.ForeignKey("enquiries.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "service_offer_id", UUID(as_uuid=True),
            sa.ForeignKey("service_offers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "amount", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column(
            "brain_version_id", UUID(as_uuid=True),
            sa.ForeignKey("brain_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pricing_evidence", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
    op.create_index("ix_quotes_customer_id", "quotes", ["customer_id"])
    op.create_index("ix_quotes_business_id", "quotes", ["business_id"])
    op.create_index("ix_quotes_enquiry_id", "quotes", ["enquiry_id"])
    op.create_index("ix_quotes_status", "quotes", ["status"])
    op.create_index("ix_quotes_reference", "quotes", ["reference"])

    # --- bookings ---
    op.create_table(
        "bookings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "customer_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "business_id", UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "quote_id", UUID(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "enquiry_id", UUID(as_uuid=True),
            sa.ForeignKey("enquiries.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "service_offer_id", UUID(as_uuid=True),
            sa.ForeignKey("service_offers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="requested"),
        sa.Column(
            "brain_version_id", UUID(as_uuid=True),
            sa.ForeignKey("brain_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision_evidence", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
    op.create_index("ix_bookings_customer_id", "bookings", ["customer_id"])
    op.create_index("ix_bookings_business_id", "bookings", ["business_id"])
    op.create_index("ix_bookings_quote_id", "bookings", ["quote_id"])
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index("ix_bookings_reference", "bookings", ["reference"])


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("quotes")
