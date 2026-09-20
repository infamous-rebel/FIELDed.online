"""Phase 07 — enforce one ACTIVE BrainVersion per brain at database level.

Adds a partial unique index on brain_versions(brain_id) WHERE status = 'active'
AND deleted_at IS NULL.  This makes PostgreSQL the final enforcement layer for
the "one active version per business" invariant.

The application-level SELECT FOR UPDATE protection in BrainService.activate_version()
is preserved as the concurrency-control layer; this index is the data-integrity layer.

Revision ID: 006_brain_version_active_unique
Revises: 005_enquiry_brain_version
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_brain_version_active_unique"
down_revision: Union[str, None] = "005_enquiry_brain_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial unique index: at most one row per brain_id can have
    # status = 'active' AND deleted_at IS NULL.
    # BrainVersionStatus.ACTIVE persists as the lowercase string "active".
    op.create_index(
        "uq_brain_version_one_active_per_brain",
        "brain_versions",
        ["brain_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_brain_version_one_active_per_brain",
        table_name="brain_versions",
    )
