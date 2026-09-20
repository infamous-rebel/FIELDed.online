"""Phase 14B.1 — Voice / Call Agent Domain & Database Foundation.

Creates:
- voice_calls: logical voice calls (linked to Phase 14A communications)
- voice_call_participants: per-call participants (external supported)
- voice_call_attempts: provider attempts (append-oriented, unique per call)
- voice_call_sessions: conversational sessions (reference-only media)
- voice_call_escalations: explicit human escalation state
- call_agent_configurations: business Call Agent operational configuration
- communication_campaigns: minimal campaign foundation (no execution)
- campaign_recipients: per-campaign recipient state

Revision ID: 011_phase14b_voice_call_agent
Revises: 010_phase14a_communications_notifications
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "011_phase14b_voice_call_agent"
down_revision: Union[str, None] = "010_phase14a_communications_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Voice Calls ──
    op.create_table(
        "voice_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("enquiry_id", UUID(as_uuid=True), sa.ForeignKey("enquiries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quote_id", UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_execution_id", UUID(as_uuid=True), sa.ForeignKey("service_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("call_type", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="REQUESTED"),
        sa.Column("to_number", sa.String(50), nullable=False),
        sa.Column("from_number", sa.String(50), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_reference", sa.String(500), nullable=True),
        sa.Column("brain_version_id", UUID(as_uuid=True), sa.ForeignKey("brain_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("communication_id", UUID(as_uuid=True), sa.ForeignKey("communications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(500), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_calls_business_id", "voice_calls", ["business_id"])
    op.create_index("ix_voice_calls_customer_id", "voice_calls", ["customer_id"])
    op.create_index("ix_voice_calls_status", "voice_calls", ["status"])
    op.create_index("ix_voice_calls_call_type", "voice_calls", ["call_type"])
    op.create_index("ix_voice_calls_purpose", "voice_calls", ["purpose"])
    op.create_index("ix_voice_calls_communication_id", "voice_calls", ["communication_id"])
    # Idempotency: unique per business, active rows only
    op.create_index(
        "uq_voice_calls_business_idempotency",
        "voice_calls",
        ["business_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── Voice Call Participants ──
    op.create_table(
        "voice_call_participants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", UUID(as_uuid=True), sa.ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_type", sa.String(50), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("business_member_id", UUID(as_uuid=True), sa.ForeignKey("business_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_call_participants_call_id", "voice_call_participants", ["call_id"])
    op.create_index("ix_voice_call_participants_user_id", "voice_call_participants", ["user_id"])

    # ── Voice Call Attempts (append-oriented) ──
    op.create_table(
        "voice_call_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", UUID(as_uuid=True), sa.ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_reference", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="REQUESTED"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("retryable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("provider_payload_reference", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("call_id", "attempt_number", name="uq_voice_call_attempts_call_attempt"),
    )
    op.create_index("ix_voice_call_attempts_call_id", "voice_call_attempts", ["call_id"])

    # ── Voice Call Sessions ──
    op.create_table(
        "voice_call_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", UUID(as_uuid=True), sa.ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_session_reference", sa.String(500), nullable=True),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("transcript_reference", sa.String(500), nullable=True),
        sa.Column("recording_reference", sa.String(500), nullable=True),
        sa.Column("human_escalation_requested", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("human_escalation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_call_sessions_call_id", "voice_call_sessions", ["call_id"])

    # ── Voice Call Escalations ──
    op.create_table(
        "voice_call_escalations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", UUID(as_uuid=True), sa.ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("escalation_status", sa.String(50), nullable=False, server_default="REQUESTED"),
        sa.Column("escalation_reason", sa.Text, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_member_id", UUID(as_uuid=True), sa.ForeignKey("business_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_call_escalations_call_id", "voice_call_escalations", ["call_id"])
    op.create_index("ix_voice_call_escalations_status", "voice_call_escalations", ["escalation_status"])

    # ── Call Agent Configurations ──
    op.create_table(
        "call_agent_configurations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("transactional_calling_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("marketing_calling_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("default_from_number", sa.String(50), nullable=True),
        sa.Column("provider_reference", sa.String(500), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=True),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("retry_interval_seconds", sa.Integer, nullable=False, server_default="300"),
        sa.Column("allowed_calling_hours", JSONB, nullable=True),
        sa.Column("quiet_periods", JSONB, nullable=True),
        sa.Column("max_daily_attempts", sa.Integer, nullable=True),
        sa.Column("max_weekly_attempts", sa.Integer, nullable=True),
        sa.Column("customer_frequency_limits", JSONB, nullable=True),
        sa.Column("human_escalation_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("recording_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("transcription_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_call_agent_configurations_business_id", "call_agent_configurations", ["business_id"])
    op.create_index(
        "uq_call_agent_configurations_business",
        "call_agent_configurations",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── Communication Campaigns ──
    op.create_table(
        "communication_campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="DRAFT"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("brain_version_id", UUID(as_uuid=True), sa.ForeignKey("brain_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_communication_campaigns_business_id", "communication_campaigns", ["business_id"])
    op.create_index("ix_communication_campaigns_status", "communication_campaigns", ["status"])
    op.create_index("ix_communication_campaigns_channel", "communication_campaigns", ["channel"])
    op.create_index("ix_communication_campaigns_purpose", "communication_campaigns", ["purpose"])

    # ── Campaign Recipients ──
    op.create_table(
        "campaign_recipients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("communication_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_campaign_recipients_campaign_id", "campaign_recipients", ["campaign_id"])
    op.create_index("ix_campaign_recipients_customer_id", "campaign_recipients", ["customer_id"])
    op.create_index("ix_campaign_recipients_status", "campaign_recipients", ["status"])


def downgrade() -> None:
    op.drop_table("campaign_recipients")
    op.drop_table("communication_campaigns")
    op.drop_table("call_agent_configurations")
    op.drop_table("voice_call_escalations")
    op.drop_table("voice_call_sessions")
    op.drop_table("voice_call_attempts")
    op.drop_table("voice_call_participants")
    op.drop_table("voice_calls")
