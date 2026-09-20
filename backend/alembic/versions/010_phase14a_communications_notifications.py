"""Phase 14A — Communications, Notifications, Outbox & Provider Infrastructure.

Creates:
- communications: core communication records
- communication_recipients: per-communication recipients
- communication_attempts: provider delivery attempts (append-only)
- communication_templates: template identity
- communication_template_versions: immutable template content
- business_communication_channels: operational channel config
- business_communication_purposes: operational purpose config
- customer_communication_preferences: consent/preferences
- notifications: persisted notification records
- outbox_events: transactional outbox for event-driven processing
- communication_webhooks: inbound provider webhook events
- communication_audit_events: immutable audit trail

Revision ID: 010_phase14a_communications_notifications
Revises: 009_phase13_service_execution_invoice_ledger
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "010_phase14a_communications_notifications"
down_revision: Union[str, None] = "009_phase13_service_execution_invoice_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Communications ──
    op.create_table(
        "communications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(500), nullable=False, unique=True),
        sa.Column("brain_version_id", UUID(as_uuid=True), sa.ForeignKey("brain_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_evidence", JSONB, nullable=True),
        sa.Column("enquiry_id", UUID(as_uuid=True), sa.ForeignKey("enquiries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quote_id", UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_execution_id", UUID(as_uuid=True), sa.ForeignKey("service_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_reference", sa.String(500), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_communications_business_id", "communications", ["business_id"])
    op.create_index("ix_communications_customer_id", "communications", ["customer_id"])
    op.create_index("ix_communications_status", "communications", ["status"])
    op.create_index("ix_communications_channel", "communications", ["channel"])
    op.create_index("ix_communications_purpose", "communications", ["purpose"])

    # ── Communication Recipients ──
    op.create_table(
        "communication_recipients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("communication_id", UUID(as_uuid=True), sa.ForeignKey("communications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_type", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comm_recipients_communication_id", "communication_recipients", ["communication_id"])
    op.create_index("ix_comm_recipients_user_id", "communication_recipients", ["user_id"])

    # ── Communication Attempts (append-only, no soft-delete) ──
    op.create_table(
        "communication_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("communication_id", UUID(as_uuid=True), sa.ForeignKey("communications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("provider_reference", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("provider_response", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comm_attempts_communication_id", "communication_attempts", ["communication_id"])

    # ── Communication Templates ──
    op.create_table(
        "communication_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active_version_id", UUID(as_uuid=True), nullable=True),  # FK added after versions table
        sa.Column("status", sa.String(50), nullable=False, server_default="DRAFT"),
        sa.Column("approval_state", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comm_templates_business_id", "communication_templates", ["business_id"])
    op.create_index("ix_comm_templates_channel", "communication_templates", ["channel"])
    op.create_index("ix_comm_templates_purpose", "communication_templates", ["purpose"])

    # ── Communication Template Versions (immutable, no soft-delete) ──
    op.create_table(
        "communication_template_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("communication_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("variables", JSONB, nullable=True),
        sa.Column("approval_provenance", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("template_id", "version_number", name="uq_template_version_number"),
    )
    op.create_index("ix_comm_template_versions_template_id", "communication_template_versions", ["template_id"])

    # Add FK from templates → versions (deferred to avoid circular dependency)
    op.create_foreign_key(
        "fk_templates_active_version",
        "communication_templates",
        "communication_template_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Business Communication Channels ──
    op.create_table(
        "business_communication_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("provider_ref", sa.String(100), nullable=True),
        sa.Column("settings", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index(
            "uq_bcc_business_channel",
            "business_id",
            "channel",
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
    )
    op.create_index("ix_bcc_business_id", "business_communication_channels", ["business_id"])

    # ── Business Communication Purposes ──
    op.create_table(
        "business_communication_purposes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("permitted_channels", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index(
            "uq_bcp_business_purpose",
            "business_id",
            "purpose",
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
    )
    op.create_index("ix_bcp_business_id", "business_communication_purposes", ["business_id"])

    # ── Customer Communication Preferences ──
    op.create_table(
        "customer_communication_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=True),
        sa.Column("purpose", sa.String(50), nullable=True),
        sa.Column("consent_state", sa.String(50), nullable=False, server_default="UNKNOWN"),
        sa.Column("opt_in", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("suppression", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("suppression_reason", sa.Text, nullable=True),
        sa.Column("do_not_contact", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ccp_customer_id", "customer_communication_preferences", ["customer_id"])
    op.create_index("ix_ccp_business_id", "customer_communication_preferences", ["business_id"])
    # Expression unique index for NULL wildcard semantics
    op.create_index(
        "uq_ccp_customer_business_channel_purpose",
        "customer_communication_preferences",
        ["customer_id", "business_id", sa.text("COALESCE(channel, '__ALL__')"), sa.text("COALESCE(purpose, '__ALL__')")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── Notifications ──
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notification_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("priority", sa.String(50), nullable=False, server_default="NORMAL"),
        sa.Column("idempotency_key", sa.String(500), nullable=False, unique=True),
        sa.Column("related_entity_type", sa.String(100), nullable=True),
        sa.Column("related_entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_state", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_business_id", "notifications", ["business_id"])
    op.create_index("ix_notifications_customer_id", "notifications", ["customer_id"])
    op.create_index("ix_notifications_type", "notifications", ["notification_type"])
    op.create_index("ix_notifications_customer_unread", "notifications", ["customer_id", "read_at"])

    # ── Outbox Events (no soft-delete) ──
    op.create_table(
        "outbox_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("idempotency_key", sa.String(500), nullable=False, unique=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_business_id", "outbox_events", ["business_id"])
    op.create_index("ix_outbox_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])
    op.create_index("ix_outbox_status_available", "outbox_events", ["status", "available_at"])
    op.create_index("ix_outbox_event_type", "outbox_events", ["event_type"])

    # ── Communication Webhooks (immutable, no soft-delete) ──
    op.create_table(
        "communication_webhooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("external_event_id", sa.String(500), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("communication_id", UUID(as_uuid=True), sa.ForeignKey("communications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("processing_status", sa.String(50), nullable=False, server_default="RECEIVED"),
        sa.Column("error_metadata", JSONB, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_webhooks_provider_external"),
    )
    op.create_index("ix_comm_webhooks_provider", "communication_webhooks", ["provider"])
    op.create_index("ix_comm_webhooks_communication_id", "communication_webhooks", ["communication_id"])

    # ── Communication Audit Events (append-only, no soft-delete) ──
    op.create_table(
        "communication_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(50), nullable=True),
        sa.Column("purpose", sa.String(50), nullable=True),
        sa.Column("communication_id", UUID(as_uuid=True), sa.ForeignKey("communications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("brain_version_id", UUID(as_uuid=True), sa.ForeignKey("brain_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_evidence", JSONB, nullable=True),
        sa.Column("provider_reference", sa.String(500), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comm_audit_business_id", "communication_audit_events", ["business_id"])
    op.create_index("ix_comm_audit_customer_id", "communication_audit_events", ["customer_id"])
    op.create_index("ix_comm_audit_communication_id", "communication_audit_events", ["communication_id"])
    op.create_index("ix_comm_audit_event_type", "communication_audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("communication_audit_events")
    op.drop_table("communication_webhooks")
    op.drop_table("outbox_events")
    op.drop_table("notifications")
    op.drop_table("customer_communication_preferences")
    op.drop_table("business_communication_purposes")
    op.drop_table("business_communication_channels")
    op.drop_table("communication_template_versions")
    op.drop_table("communication_templates")
    op.drop_table("communication_attempts")
    op.drop_table("communication_recipients")
    op.drop_table("communications")
