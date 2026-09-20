"""Phase 14B.2 — voice runtime, agent session state, webhook linkage.

Adds:
- voice_calls.campaign_id: campaign linkage for campaign-executed calls
- voice_call_sessions: Call Agent runtime state (collected_information,
  conversation_log, turn_count, outcome, outcome_summary)
- call_agent_configurations: agent_instructions (operational style only),
  webhook_signature_secret (provider callback validation)
- communication_webhooks.voice_call_id: voice provider callbacks link
  to the voice call (single provider-event store across channels)

Revision ID: 012_phase14b_voice_runtime
Revises: 011_phase14b_voice_call_agent
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "012_phase14b_voice_runtime"
down_revision: Union[str, None] = "011_phase14b_voice_call_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. voice_calls.campaign_id
    op.add_column(
        "voice_calls",
        sa.Column("campaign_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_voice_calls_campaign_id",
        "voice_calls",
        "communication_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_voice_calls_campaign_id", "voice_calls", ["campaign_id"]
    )

    # 2. voice_call_sessions — Call Agent runtime state
    op.add_column(
        "voice_call_sessions",
        sa.Column("collected_information", JSONB, nullable=True),
    )
    op.add_column(
        "voice_call_sessions",
        sa.Column("conversation_log", JSONB, nullable=True),
    )
    op.add_column(
        "voice_call_sessions",
        sa.Column(
            "turn_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "voice_call_sessions",
        sa.Column("outcome", sa.String(50), nullable=True),
    )
    op.add_column(
        "voice_call_sessions",
        sa.Column("outcome_summary", sa.Text(), nullable=True),
    )

    # 3. call_agent_configurations — operational agent/webhook settings
    op.add_column(
        "call_agent_configurations",
        sa.Column("agent_instructions", sa.Text(), nullable=True),
    )
    op.add_column(
        "call_agent_configurations",
        sa.Column(
            "webhook_signature_secret", sa.String(255), nullable=True
        ),
    )

    # 4. communication_webhooks.voice_call_id
    op.add_column(
        "communication_webhooks",
        sa.Column("voice_call_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_comm_webhooks_voice_call_id",
        "communication_webhooks",
        "voice_calls",
        ["voice_call_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_comm_webhooks_voice_call_id",
        "communication_webhooks",
        ["voice_call_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comm_webhooks_voice_call_id", table_name="communication_webhooks"
    )
    op.drop_constraint(
        "fk_comm_webhooks_voice_call_id", "communication_webhooks", type_="foreignkey"
    )
    op.drop_column("communication_webhooks", "voice_call_id")

    op.drop_column("call_agent_configurations", "webhook_signature_secret")
    op.drop_column("call_agent_configurations", "agent_instructions")

    op.drop_column("voice_call_sessions", "outcome_summary")
    op.drop_column("voice_call_sessions", "outcome")
    op.drop_column("voice_call_sessions", "turn_count")
    op.drop_column("voice_call_sessions", "conversation_log")
    op.drop_column("voice_call_sessions", "collected_information")

    op.drop_index("ix_voice_calls_campaign_id", table_name="voice_calls")
    op.drop_constraint(
        "fk_voice_calls_campaign_id", "voice_calls", type_="foreignkey"
    )
    op.drop_column("voice_calls", "campaign_id")
