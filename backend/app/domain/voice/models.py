"""Voice / Call Agent domain models.

Phase 14B.1 — Voice / Call Agent Domain & Database Foundation.

A VoiceCall hangs off the existing Phase 14A Communication entity
(nullable FK) rather than forming a parallel communication system.
Child records (participants, attempts, sessions, escalations) are
scoped through their parent call.  Transcripts and recordings are
stored as references only — never as large payloads in PostgreSQL.
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
    from app.domain.communication.models import Communication
    from app.domain.identity.models import Business, BusinessMember, User


class VoiceCall(BaseModel):
    """A logical voice call.

    Represents one logical call request — a single call may involve
    multiple provider attempts (VoiceCallAttempt) and one conversational
    session once connected (VoiceCallSession).  All lifecycle state
    changes flow through the deterministic call state machine.

    Relationship anchors are all optional: a call may be initiated
    because of an enquiry, quote, booking, service execution, invoice,
    campaign, or human escalation without forcing every relationship.
    """

    __tablename__ = "voice_calls"
    __table_args__ = (
        Index("ix_voice_calls_business_id", "business_id"),
        Index("ix_voice_calls_customer_id", "customer_id"),
        Index("ix_voice_calls_status", "status"),
        Index("ix_voice_calls_call_type", "call_type"),
        Index("ix_voice_calls_purpose", "purpose"),
        Index("ix_voice_calls_communication_id", "communication_id"),
        # Idempotency: unique per business — repeated requests using the
        # same idempotency key must not create duplicate logical calls.
        Index(
            "uq_voice_calls_business_idempotency",
            "business_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    # Tenant anchor
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

    # Optional relationship anchors — server-resolved
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

    # Call classification
    call_type: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="REQUESTED")

    # Phone routing
    to_number: Mapped[str] = mapped_column(String(50), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Provider tracking
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Brain traceability — the Brain version governing this call
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Phase 14A Communication integration — preferred relationship:
    # Communication -> VoiceCall
    communication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communications.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Campaign linkage — set when the call was placed by campaign
    # execution (14B.2).  Nullable: manual/transactional calls have
    # no campaign.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communication_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Idempotency (uniqueness enforced per business via partial index)
    idempotency_key: Mapped[str] = mapped_column(String(500), nullable=False)

    # Lifecycle timestamps
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Failure details
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    customer: Mapped[User | None] = relationship(foreign_keys=[customer_id])
    brain_version: Mapped[BrainVersion | None] = relationship(foreign_keys=[brain_version_id])
    communication: Mapped[Communication | None] = relationship(foreign_keys=[communication_id])
    campaign: Mapped[CommunicationCampaign | None] = relationship(foreign_keys=[campaign_id])
    participants: Mapped[list[VoiceCallParticipant]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    attempts: Mapped[list[VoiceCallAttempt]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[VoiceCallSession]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    escalations: Mapped[list[VoiceCallEscalation]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class VoiceCallParticipant(BaseModel):
    """A participant on a voice call.

    Supports customers, business members, the Call Agent, human
    agents, and external parties.  Identifiers are nullable because a
    phone number alone is sufficient for legitimate external
    participants without a FIELDed user account.
    """

    __tablename__ = "voice_call_participants"
    __table_args__ = (
        Index("ix_voice_call_participants_call_id", "call_id"),
        Index("ix_voice_call_participants_user_id", "user_id"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_calls.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    business_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    call: Mapped[VoiceCall] = relationship(back_populates="participants")
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])


class VoiceCallAttempt(BaseModel):
    """A single provider attempt for a logical call.

    Append-oriented: a logical call may have multiple provider
    attempts and historical attempts are never overwritten to make a
    later attempt appear as the original.  This table does not use
    soft deletion in practice — rows are only created, never mutated
    into a different attempt.
    """

    __tablename__ = "voice_call_attempts"
    __table_args__ = (
        Index("ix_voice_call_attempts_call_id", "call_id"),
        # One attempt per (call, attempt number)
        Index(
            "uq_voice_call_attempts_call_attempt",
            "call_id",
            "attempt_number",
            unique=True,
        ),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_calls.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="REQUESTED")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_payload_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    call: Mapped[VoiceCall] = relationship(back_populates="attempts")


class VoiceCallSession(BaseModel):
    """The conversational session of a connected call.

    Exists only while the call is connected.  Transcripts and
    recordings are stored as references to the storage/integration
    layer — never as large payloads in PostgreSQL.  References remain
    nullable until recording/transcription processing is implemented
    in a later 14B block.
    """

    __tablename__ = "voice_call_sessions"
    __table_args__ = (Index("ix_voice_call_sessions_call_id", "call_id"),)

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_calls.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent_session_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # References to future storage/integration layer
    transcript_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Human escalation markers (state persisted in VoiceCallEscalation)
    human_escalation_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_escalation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Phase 14B.2 — Call Agent runtime state
    # Structured information collected during the conversation
    # (validated against governed collectible fields before write).
    collected_information: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Append-only turn log: [{"role": ..., "content": ..., "action": ..., "at": ...}]
    conversation_log: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Recorded outcome (CallOutcome values) + free-text summary
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    call: Mapped[VoiceCall] = relationship(back_populates="sessions")


class VoiceCallEscalation(BaseModel):
    """Explicit persisted human escalation state.

    Supports: Call Agent → human escalation requested → business
    member assigned → human accepts → agent hands off.  Escalation is
    never represented merely as a string inside a JSON blob.
    """

    __tablename__ = "voice_call_escalations"
    __table_args__ = (
        Index("ix_voice_call_escalations_call_id", "call_id"),
        Index("ix_voice_call_escalations_status", "escalation_status"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_calls.id", ondelete="CASCADE"),
        nullable=False,
    )
    escalation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="REQUESTED")
    escalation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    call: Mapped[VoiceCall] = relationship(back_populates="escalations")
    assigned_member: Mapped[BusinessMember | None] = relationship(foreign_keys=[assigned_member_id])


class CallAgentConfiguration(BaseModel):
    """Business-level Call Agent operational configuration.

    Dedicated operational configuration for frequently changing
    operational settings (enablement, phone number, provider
    reference, retry settings, calling windows).  Governed behavior —
    permitted purposes, escalation rules, agent behavior, approved
    scripts — remains controlled by BrainVersion.communication_config.
    This table never competes with Business Brain governance.
    """

    __tablename__ = "call_agent_configurations"
    __table_args__ = (
        Index("ix_call_agent_configurations_business_id", "business_id"),
        # One operational configuration per business
        Index(
            "uq_call_agent_configurations_business",
            "business_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Enablement — transactional and marketing calling are independent
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transactional_calling_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    marketing_calling_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Phone/provider operational settings
    default_from_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Operational retry settings
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)

    # Calling windows and frequency caps
    # JSONB structures:
    #   allowed_calling_hours: {"start": "09:00", "end": "18:00", "days": [...]}
    #   quiet_periods: [{"start": "...", "end": "..."}]
    #   customer_frequency_limits: {"per_day": n, "per_week": n}
    allowed_calling_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    quiet_periods: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    max_daily_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_weekly_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_frequency_limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Capability toggles
    human_escalation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recording_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transcription_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Phase 14B.2 — agent operational overrides and webhook security.
    # Governed agent behavior still lives ONLY in
    # BrainVersion.communication_config['voice_agent']; this field is
    # operational style/tone supplement, never policy authority.
    agent_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_signature_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CommunicationCampaign(BaseModel):
    """A communication campaign.

    Minimal persistent campaign foundation.  Campaign execution
    (audience selection, scheduling, bulk calls, automated retries,
    analytics) belongs to later 14B blocks — this model establishes
    the tenant-scoped identity and lifecycle only.  Campaigns remain
    subject to the existing consent/suppression/DNC/frequency/timing/
    Business Brain/authorization policy chain at execution time.
    """

    __tablename__ = "communication_campaigns"
    __table_args__ = (
        Index("ix_communication_campaigns_business_id", "business_id"),
        Index("ix_communication_campaigns_status", "status"),
        Index("ix_communication_campaigns_channel", "channel"),
        Index("ix_communication_campaigns_purpose", "purpose"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Channel uses CommunicationChannel values; purpose uses CallPurpose
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")

    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Brain version governing the campaign
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    brain_version: Mapped[BrainVersion | None] = relationship(foreign_keys=[brain_version_id])
    recipients: Mapped[list[CampaignRecipient]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignRecipient(BaseModel):
    """A recipient within a campaign.

    Tracks per-recipient state for future campaign execution.
    Recipients never bypass the existing consent/suppression/DNC/
    frequency/timing/Business Brain/authorization policy chain —
    eligibility evaluation happens at execution time (later block).
    """

    __tablename__ = "campaign_recipients"
    __table_args__ = (
        Index("ix_campaign_recipients_campaign_id", "campaign_id"),
        Index("ix_campaign_recipients_customer_id", "customer_id"),
        Index("ix_campaign_recipients_status", "status"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("communication_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    campaign: Mapped[CommunicationCampaign] = relationship(back_populates="recipients")
