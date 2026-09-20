"""Phase 12 closure — currency columns for business, booking.

Adds:
- businesses.currency: the business's operational currency (ISO 4217)
- bookings.currency: transaction currency inherited from Quote at creation

Revision ID: 008_currency_columns
Revises: 007_quote_booking
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_currency_columns"
down_revision: Union[str, None] = "007_quote_booking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add currency to businesses (operational currency setting)
    op.add_column(
        "businesses",
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
    )

    # Add currency to bookings (transaction currency, inherited from quote)
    op.add_column(
        "bookings",
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
    )


def downgrade() -> None:
    op.drop_column("bookings", "currency")
    op.drop_column("businesses", "currency")
