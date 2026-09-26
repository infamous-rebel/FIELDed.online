"""Stripe webhook event idempotency model.

Tracks every processed Stripe webhook event to guarantee idempotent
processing.  Duplicate deliveries from Stripe are detected by the
unique ``stripe_event_id`` constraint and silently acknowledged.

This model is the single source of truth for "has FIELDed already
processed this Stripe event?" — it is NOT a general audit log
(though it carries the raw payload for evidence).

Tenant isolation: each event is linked to the business that owns
the payment it relates to.  Events without a known payment are
still recorded (with business_id=None) so they are not re-processed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business
    from app.domain.payment.models import Payment


class StripeEvent(BaseModel):
    """A processed Stripe webhook event.

    Created by the reconciliation service when a webhook is first
    processed.  Duplicate deliveries find the existing row via
    ``stripe_event_id`` and are acknowledged without re-processing.
    """

    __tablename__ = "stripe_events"
    __table_args__ = (
        # Stripe event IDs are globally unique (evt_xxx)
        UniqueConstraint("stripe_event_id", name="uq_stripe_events_event_id"),
        Index("ix_stripe_events_business_id", "business_id"),
        Index("ix_stripe_events_payment_id", "payment_id"),
        Index("ix_stripe_events_payment_intent_id", "payment_intent_id"),
        Index("ix_stripe_events_event_type", "event_type"),
        Index("ix_stripe_events_created_at", "created_at"),
    )

    # Stripe's event ID (evt_xxx) — the idempotency key
    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Stripe event type (e.g. payment_intent.succeeded)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # The PaymentIntent this event relates to (pi_xxx)
    payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Stripe connected account that sent the event (acct_xxx)
    # Used for tenant isolation verification
    stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # FIELDed business (resolved from the payment, not from Stripe)
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
    )

    # FIELDed payment (resolved from provider_reference)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Processing outcome
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="processed")
    # "processed" — successfully reconciled
    # "duplicate" — already seen, acknowledged
    # "unknown_payment" — no matching FIELDed payment found
    # "tenant_mismatch" — Stripe account didn't match business
    # "error" — processing failed, evidence preserved
    # "ignored" — event type not relevant to FIELDed

    # Error details (if status = "error")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full raw Stripe event payload for evidence/audit
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # When the event was created in Stripe
    stripe_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    business: Mapped[Business | None] = relationship(foreign_keys=[business_id])
    payment: Mapped[Payment | None] = relationship(foreign_keys=[payment_id])
