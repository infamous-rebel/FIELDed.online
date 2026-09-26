"""Phase 19B — Stripe Connect payment foundation.

Adds Stripe Connect columns to the businesses table:
- stripe_account_id: connected Stripe account ID (acct_xxx)
- stripe_connect_status: onboarding/capability status
- stripe_charges_enabled: whether charges are enabled on the account
- stripe_payouts_enabled: whether payouts are enabled on the account
- stripe_details: JSONB snapshot of Stripe account details
- platform_fee_percent: platform application fee percentage

Revision ID: 017_stripe_connect
Revises: 016_phase18_brain_conversation
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "017_stripe_connect"
down_revision: str | None = "016_phase18_brain_conversation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("stripe_account_id", sa.String(255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_businesses_stripe_account_id",
        "businesses",
        ["stripe_account_id"],
    )
    op.add_column(
        "businesses",
        sa.Column(
            "stripe_connect_status",
            sa.String(50),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "stripe_charges_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "stripe_payouts_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "businesses",
        sa.Column("stripe_details", JSONB, nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "platform_fee_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
    )


def downgrade() -> None:
    op.drop_column("businesses", "platform_fee_percent")
    op.drop_column("businesses", "stripe_details")
    op.drop_column("businesses", "stripe_payouts_enabled")
    op.drop_column("businesses", "stripe_charges_enabled")
    op.drop_column("businesses", "stripe_connect_status")
    op.drop_constraint("uq_businesses_stripe_account_id", "businesses", type_="unique")
    op.drop_column("businesses", "stripe_account_id")
