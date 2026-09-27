"""Brain message structured response.

Adds a structured_response JSONB column to brain_messages to store
validated semantic block representations of Brain responses alongside
the existing plain-text content.

This enables the frontend to render semantic blocks (observations,
recommendations, proposals, etc.) while preserving backward compatibility
with historical messages that have no structured data.

Revision ID: 023_brain_message_structured_response
Revises: 022_booking_automation_status
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "023_brain_message_structured_response"
down_revision: str = "022_booking_automation_status"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brain_messages",
        sa.Column("structured_response", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brain_messages", "structured_response")
