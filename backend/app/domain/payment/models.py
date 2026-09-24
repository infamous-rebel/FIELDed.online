"""Payment domain model.

A Payment represents a financial transaction initiated against an
Invoice.  Each Payment may have multiple PaymentAttempts (e.g. retries
or provider failures).

Payment amounts and currency are persisted explicitly.
No LLM determines payment amount, authorization, transaction state,
or refund eligibility — all are deterministic.

Idempotency: the idempotency_key column has a unique constraint
ensuring no duplicate payment is created for the same logical request.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business, User
    from app.domain.invoice.models import Invoice


class Payment(BaseModel):
    """A financial payment transaction.

    Lifecycle:
        PENDING -> PROCESSING -> SUCCEEDED
        PENDING -> FAILED / EXPIRED / CANCELLED
        PROCESSING -> SUCCEEDED / FAILED / EXPIRED / CANCELLED
        SUCCEEDED -> REFUNDED / PARTIALLY_REFUNDED
        PARTIALLY_REFUNDED -> REFUNDED

    Tenant isolation: every payment belongs to exactly one business
    and one customer.  Cross-tenant access is impossible by design.
    """

    __tablename__ = "payments"
    __table_args__ = (
        # Idempotency: one payment per idempotency key
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        Index("ix_payments_business_id", "business_id"),
        Index("ix_payments_customer_id", "customer_id"),
        Index("ix_payments_invoice_id", "invoice_id"),
        Index("ix_payments_status", "status"),
        Index("ix_payments_provider_reference", "provider_reference"),
    )

    # Idempotency key — unique per logical payment request
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    # Relationship anchors — server-resolved
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Payment details
    amount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False, default="card")  # PaymentMethod enum value

    # Lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # PaymentStatus enum value

    # Provider tracking
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="stub")
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Refund tracking
    refunded_amount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    refund_provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Evidence / metadata
    provider_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    invoice: Mapped[Invoice | None] = relationship(foreign_keys=[invoice_id])
    attempts: Mapped[list[PaymentAttempt]] = relationship(back_populates="payment", cascade="all, delete-orphan")


class PaymentAttempt(BaseModel):
    """A single provider attempt for a payment.

    Append-only: each retry creates a new PaymentAttempt row.
    Historical attempts are never overwritten.
    """

    __tablename__ = "payment_attempts"
    __table_args__ = (
        Index("ix_payment_attempts_payment_id", "payment_id"),
        Index("ix_payment_attempts_provider_reference", "provider_reference"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Attempt sequence (1-based, monotonically increasing per payment)
    attempt_number: Mapped[int] = mapped_column(default=1, nullable=False)

    # Provider details
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="stub")
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Result
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # "pending", "processing", "succeeded", "failed"
    amount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # Timing
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Error details
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw provider response for audit
    provider_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    payment: Mapped[Payment] = relationship(back_populates="attempts")
