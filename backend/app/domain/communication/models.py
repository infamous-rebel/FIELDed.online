"""Communication domain models.

Core communication records, recipients, attempts, templates,
operational configuration, consent/preferences, webhooks, and audit.

Phase 14A — Core Communications, Notifications & Provider Adapters.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.business.models import BrainVersion
    from app.domain.identity.models import Business, User


class Communication(BaseModel):
    """Core communication record.

    Represents a single communication sent (or attempted) through
    a provider adapter.  Each communication has exactly one channel,
    one purpose, and one or more recipients.
    """

    __tablename__ = "communications"
    __table_args__ = (
        Index("ix_communications_business_id", "business_id"),
        Index("ix_communications_customer_id", "customer_id"),
        Index("ix_communications_status", "status"),
        Index("ix_communications_channel", "channel"),
        Index("ix_communications_purpose", "purpose"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")

    # Idempotency — unique constraint prevents duplicate communications
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)

    # Brain traceability
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Related entity references (all nullable)
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enquiries.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Provider tracking
    provider_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    customer: Mapped[User | None] = relationship(foreign_keys=[customer_id])
    brain_version: Mapped[BrainVersion | None] = relationship(foreign_keys=[brain_version_id])
    recipients: Mapped[list[CommunicationRecipient]] = relationship(
        back_populates="communication", cascade="all, delete-orphan"
    )
    attempts: Mapped[list[CommunicationAttempt]] = relationship(
        back_populates="communication", cascade="all, delete-orphan"
    )


class CommunicationRecipient(BaseModel):
    """A recipient of a communication.

    Supports customers, staff, external recipients, and other
    authorized recipients.  user_id is nullable to support external
    recipients without a FIELDed user account.
    """

    __tablename__ = "communication_recipients"
    __table_args__ = (
        Index("ix_comm_recipients_communication_id", "communication_id"),
        Index("ix_comm_recipients_user_id", "user_id"),
    )

    communication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_type: Mapped[str] = mapped_column(String(50), nullable=False)  # RecipientType enum value
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)  # email/phone/device token
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")

    # Relationships
    communication: Mapped[Communication] = relationship(back_populates="recipients")
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])


class CommunicationAttempt(BaseModel):
    """A provider delivery attempt.

    Every actual provider interaction produces one attempt record.
    A communication may have multiple attempts (retries).

    This table is append-oriented and does NOT use soft deletion.
    """

    __tablename__ = "communication_attempts"
    __table_args__ = (Index("ix_comm_attempts_communication_id", "communication_id"),)

    communication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    communication: Mapped[Communication] = relationship(back_populates="attempts")


class CommunicationTemplate(BaseModel):
    """Stable template identity.

    The template represents the current/active version.
    Historical content is stored in CommunicationTemplateVersion.
    """

    __tablename__ = "communication_templates"
    __table_args__ = (
        Index("ix_comm_templates_business_id", "business_id"),
        Index("ix_comm_templates_channel", "channel"),
        Index("ix_comm_templates_purpose", "purpose"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communication_template_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    approval_state: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")

    # Relationships
    versions: Mapped[list[CommunicationTemplateVersion]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        foreign_keys="CommunicationTemplateVersion.template_id",
    )


class CommunicationTemplateVersion(BaseModel):
    """Immutable historical template content.

    Each version is a snapshot of the template at a point in time.
    Previously used versions remain reproducible.

    This table does NOT use soft deletion (immutable records).
    """

    __tablename__ = "communication_template_versions"
    __table_args__ = (Index("ix_comm_template_versions_template_id", "template_id"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communication_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approval_provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    template: Mapped[CommunicationTemplate] = relationship(
        back_populates="versions",
        foreign_keys=[template_id],
    )


class BusinessCommunicationChannel(BaseModel):
    """Operational channel configuration for a business.

    Controls whether a channel is enabled and which provider to use.
    """

    __tablename__ = "business_communication_channels"
    __table_args__ = (
        Index("ix_bcc_business_id", "business_id"),
        # Unique constraint: one config per business per channel
        Index(
            "uq_bcc_business_channel",
            "business_id",
            "channel",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class BusinessCommunicationPurpose(BaseModel):
    """Operational purpose configuration for a business.

    Controls whether a purpose is enabled and which channels are permitted.
    """

    __tablename__ = "business_communication_purposes"
    __table_args__ = (
        Index("ix_bcp_business_id", "business_id"),
        Index(
            "uq_bcp_business_purpose",
            "business_id",
            "purpose",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    permitted_channels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CustomerCommunicationPreference(BaseModel):
    """Customer communication consent and preferences.

    Supports channel-specific and purpose-specific consent.
    Nullable channel/purpose means the preference applies to all.
    """

    __tablename__ = "customer_communication_preferences"
    __table_args__ = (
        Index("ix_ccp_customer_id", "customer_id"),
        Index("ix_ccp_business_id", "business_id"),
        # Expression unique index to handle NULL wildcard semantics
        Index(
            "uq_ccp_customer_business_channel_purpose",
            "customer_id",
            "business_id",
            text("COALESCE(channel, '__ALL__')"),
            text("COALESCE(purpose, '__ALL__')"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)  # NULL = all channels
    purpose: Mapped[str | None] = mapped_column(String(50), nullable=True)  # NULL = all purposes
    consent_state: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppression: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunicationWebhook(BaseModel):
    """Inbound provider webhook event.

    Records external provider events for idempotent processing.
    This table does NOT use soft deletion (immutable record).
    """

    __tablename__ = "communication_webhooks"
    __table_args__ = (
        Index("ix_comm_webhooks_provider", "provider"),
        Index("ix_comm_webhooks_communication_id", "communication_id"),
        Index("ix_comm_webhooks_voice_call_id", "voice_call_id"),
        # Webhook idempotency: same provider event processed only once
        Index(
            "uq_comm_webhooks_provider_external",
            "provider",
            "external_event_id",
            unique=True,
        ),
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(500), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    communication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Phase 14B — voice provider callbacks link to the voice call.
    voice_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(50), nullable=False, default="RECEIVED")
    error_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunicationAuditEvent(BaseModel):
    """Immutable audit trail for communication lifecycle events.

    Append-only.  Does NOT use soft deletion.
    """

    __tablename__ = "communication_audit_events"
    __table_args__ = (
        Index("ix_comm_audit_business_id", "business_id"),
        Index("ix_comm_audit_customer_id", "customer_id"),
        Index("ix_comm_audit_communication_id", "communication_id"),
        Index("ix_comm_audit_event_type", "event_type"),
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(50), nullable=True)
    communication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.id", ondelete="SET NULL"),
        nullable=True,
    )
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
