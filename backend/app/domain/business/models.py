"""Business Brain domain models.

The Business Brain is the versioned operational rule system for a business.
Each business has one BusinessBrain which contains versioned configurations.
Only one version is ACTIVE at a time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel


class BusinessBrain(BaseModel):
    """The Business Brain container.

    Each business has exactly one BusinessBrain.
    The brain holds versioned configurations.
    """

    __tablename__ = "business_brains"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    versions: Mapped[list[BrainVersion]] = relationship(
        back_populates="brain", cascade="all, delete-orphan",
        foreign_keys="BrainVersion.brain_id",
    )


class BrainVersion(BaseModel):
    """A versioned snapshot of Business Brain configuration.

    Lifecycle: DRAFT -> VALIDATING -> REVIEW -> APPROVED -> ACTIVE -> SUPERSEDED
    """

    __tablename__ = "brain_versions"

    brain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_brains.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # BrainVersionStatus enum value

    # Configuration areas stored as structured JSON
    identity_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    services_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pricing_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    availability_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    qualification_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    policies_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    escalation_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    communication_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    brain: Mapped[BusinessBrain] = relationship(
        back_populates="versions",
        foreign_keys=[brain_id],
    )
    rules: Mapped[list[BusinessRule]] = relationship(
        back_populates="brain_version", cascade="all, delete-orphan"
    )


class BusinessRule(BaseModel):
    """A structured rule within a Brain version.

    Rules can be pricing, policy, qualification, availability, or escalation rules.
    The rule_type determines how the rule_data is interpreted.
    """

    __tablename__ = "business_rules"

    brain_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pricing, policy, qualification, availability, escalation
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    brain_version: Mapped[BrainVersion] = relationship(back_populates="rules")
