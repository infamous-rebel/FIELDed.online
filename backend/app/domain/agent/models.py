"""Agent capability and delegation domain models.

Provides the shared capability/delegation architecture used by all agents:
- AgentCapability: What an agent can do (capability + authority mode)
- AgentDelegation: Explicit owner delegation of a capability to an agent
- AgentExecutionLog: Audit trail of agent actions

All agent actions must flow through:
    Agent → Capability → Tool/Workflow → Permission → Delegation/Approval Policy
    → Deterministic Validation → Execution → Evidence → Audit
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel


class AgentCapability(BaseModel):
    """A capability granted to an agent type for a specific business.

    Capabilities are atomic permissions. Each capability has an authority
    mode that determines how the agent may act:
    - DISABLED: Capability not available
    - ASSIST: Agent may propose/interpret but never execute
    - APPROVAL: Agent may execute only after explicit owner approval
    - DELEGATED: Agent may execute automatically within policy bounds

    Exactly one ACTIVE capability per (business, agent_type, capability_type).
    """

    __tablename__ = "agent_capabilities"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # AgentType enum value
    capability_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # AgentCapabilityType enum value
    authority_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="disabled"
    )  # AgentAuthorityMode enum value
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Optional policy constraints for DELEGATED mode
    # e.g. {"max_amount": "1000", "currency": "GBP", "requires_enquiry": true}
    policy_constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    delegations: Mapped[list[AgentDelegation]] = relationship(
        back_populates="capability",
        cascade="all, delete-orphan",
        foreign_keys="AgentDelegation.capability_id",
    )


class AgentDelegation(BaseModel):
    """An explicit owner delegation of a capability to an agent.

    Delegations are time-bounded and can be revoked by the owner.
    When authority_mode = DELEGATED, the agent may execute the capability
    automatically within the policy constraints.

    Lifecycle: ACTIVE -> REVOKED or EXPIRED
    """

    __tablename__ = "agent_delegations"

    capability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_capabilities.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    capability_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active"
    )  # AgentDelegationStatus enum value
    granted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    capability: Mapped[AgentCapability] = relationship(
        back_populates="delegations",
        foreign_keys=[capability_id],
    )
    execution_logs: Mapped[list[AgentExecutionLog]] = relationship(
        back_populates="delegation",
        cascade="all, delete-orphan",
        foreign_keys="AgentExecutionLog.delegation_id",
    )


class AgentExecutionLog(BaseModel):
    """Audit trail of agent actions.

    Every agent action must be logged with:
    - What the agent did
    - Which capability/delegation authorized it
    - Deterministic validation results
    - Evidence (input/output)
    - Outcome

    This is the authoritative audit trail for agent actions.
    """

    __tablename__ = "agent_execution_logs"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    delegation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_delegations.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    capability_type: Mapped[str] = mapped_column(String(100), nullable=False)
    authority_mode: Mapped[str] = mapped_column(String(50), nullable=False)

    # What the agent attempted
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    action_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Deterministic validation
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Outcome
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # success, failed, blocked, error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Evidence
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Correlation
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    related_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Relationships
    delegation: Mapped[AgentDelegation | None] = relationship(
        back_populates="execution_logs",
        foreign_keys=[delegation_id],
    )
