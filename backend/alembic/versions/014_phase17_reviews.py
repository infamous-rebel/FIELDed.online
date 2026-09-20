"""Phase 17 — Reviews & Trust layer.

Adds:
- reviews: customer reviews linked to completed service executions,
  with deterministic eligibility, rating aggregation, and business
  response capability

Revision ID: 014_phase17_reviews
Revises: 013_phase15_payments
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "014_phase17_reviews"
down_revision: Union[str, None] = "013_phase15_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
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
            "service_execution_id",
            UUID(as_uuid=True),
            sa.ForeignKey("service_executions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "enquiry_id",
            UUID(as_uuid=True),
            sa.ForeignKey("enquiries.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "service_offer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("service_offers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="visible"
        ),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "responded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        # One review per completed service execution
        sa.UniqueConstraint(
            "service_execution_id",
            name="uq_reviews_service_execution_id",
        ),
    )

    # Indexes
    op.create_index(
        "ix_reviews_business_id_status", "reviews", ["business_id", "status"]
    )
    op.create_index("ix_reviews_customer_id", "reviews", ["customer_id"])


def downgrade() -> None:
    op.drop_table("reviews")
