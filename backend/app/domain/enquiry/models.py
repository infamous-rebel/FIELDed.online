"""Enquiry, Conversation, and Message domain models.

Enquiry is the customer-initiated contact entity linking a Customer,
Business, and ServiceOffer.  Each Enquiry has exactly one Conversation
(enforced by a unique constraint on conversations.enquiry_id).
Messages belong to a Conversation and support bidirectional communication.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business, User
    from app.domain.services.models import ServiceOffer


class Enquiry(BaseModel):
    """Customer-initiated enquiry about a service offer.

    An Enquiry links a Customer, Business, and ServiceOffer.
    It is always created atomically with exactly one Conversation.
    """

    __tablename__ = "enquiries"

    # Customer-friendly reference number (e.g. ENQ-a1b2c3d4)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    # Relationship anchors — server-resolved, never trusted from client
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_offers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Enquiry content
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True
    )  # EnquiryStatus enum value

    # Structured metadata (extensible for future phases)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Brain version that governed this enquiry at creation time.
    # Nullable: businesses without an active Brain will have NULL.
    # Once set, this value is immutable — it preserves historical
    # reproducibility of decisions that governed this enquiry.
    brain_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    service_offer: Mapped[ServiceOffer] = relationship(foreign_keys=[service_offer_id])
    conversation: Mapped[Conversation | None] = relationship(
        back_populates="enquiry", uselist=False, cascade="all, delete-orphan"
    )


class Conversation(BaseModel):
    """Dedicated conversation for an Enquiry.

    Exactly one Conversation per Enquiry (enforced by unique constraint
    on enquiry_id at the database level).
    """

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("enquiry_id", name="uq_conversation_enquiry"),)

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enquiries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Denormalized for efficient tenant-scoped queries
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active"
    )  # ConversationStatus enum value

    # Relationships
    enquiry: Mapped[Enquiry] = relationship(back_populates="conversation")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(BaseModel):
    """A message within a Conversation.

    Supports both customer and authorized business-member senders.
    Structured for future real-time delivery extension.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Discriminator: "customer" or "business"
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Message classification (extensible for future types)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")

    # Delivery / read tracking
    delivered_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship(foreign_keys=[sender_id])
