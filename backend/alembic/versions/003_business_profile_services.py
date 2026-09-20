"""Phase 03 — business profile + service offers.

- Add public_status column to business_profiles
- Add service_area JSONB column to business_profiles
- Add composite index on service_offers(business_id, status) for discovery queries

Revision ID: 003_business_profile_services
Revises: 002_identity_auth_tenant
Create Date: 2026-09-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "003_business_profile_services"
down_revision: Union[str, None] = "002_identity_auth_tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add public_status to business_profiles
    op.add_column(
        "business_profiles",
        sa.Column(
            "public_status",
            sa.String(50),
            nullable=False,
            server_default="incomplete",
        ),
    )

    # Add service_area JSONB to business_profiles
    op.add_column(
        "business_profiles",
        sa.Column("service_area", JSONB(), nullable=True),
    )

    # Composite index for discovery queries (active offers per business)
    op.create_index(
        "ix_service_offers_business_status",
        "service_offers",
        ["business_id", "status"],
    )

    # Index on business_profiles.public_status for public lookups
    op.create_index(
        "ix_business_profiles_public_status",
        "business_profiles",
        ["public_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_business_profiles_public_status", table_name="business_profiles")
    op.drop_index("ix_service_offers_business_status", table_name="service_offers")
    op.drop_column("business_profiles", "service_area")
    op.drop_column("business_profiles", "public_status")
