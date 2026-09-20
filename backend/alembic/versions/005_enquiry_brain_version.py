"""Phase 06 — add brain_version_id to enquiries for historical reconstruction.

Adds a nullable FK from enquiries → brain_versions so that every enquiry
retains a reference to the Business Brain version that governed it at
creation time.  This enables full historical reproducibility of decisions.

Revision ID: 005_enquiry_brain_version
Revises: 004_enquiry_conversation
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "005_enquiry_brain_version"
down_revision: Union[str, None] = "004_enquiry_conversation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enquiries",
        sa.Column(
            "brain_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brain_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_enquiries_brain_version_id",
        "enquiries",
        ["brain_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_enquiries_brain_version_id", table_name="enquiries")
    op.drop_column("enquiries", "brain_version_id")
