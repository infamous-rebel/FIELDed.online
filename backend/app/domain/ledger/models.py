"""Service Ledger domain model.

The Operational Service Ledger records every completed service as a
financial entry.  It is NOT a statutory accounting/general ledger
replacement — it tracks the operational service value for the business.

Every completed ServiceExecution produces exactly one primary ledger
entry.  Adjustments and reversals are append-oriented to preserve
historical integrity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business, User
    from app.domain.invoice.models import Invoice
    from app.domain.service_execution.models import ServiceExecution
    from app.domain.services.models import ServiceOffer


class ServiceLedgerEntry(BaseModel):
    """An operational service ledger entry.

    Created when a service execution completes.  Each completed service
    produces exactly one primary ledger entry (enforced by unique
    constraint on service_execution_id where is_primary=True).

    Adjustments/reversals reference the original entry.
    """

    __tablename__ = "service_ledger_entries"
    __table_args__ = (
        Index("ix_ledger_entries_business_id", "business_id"),
        Index("ix_ledger_entries_customer_id", "customer_id"),
        Index("ix_ledger_entries_completion_date", "completion_date"),
        Index("ix_ledger_entries_payment_status", "payment_status"),
    )

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
    service_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_offers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Completion date (the date the service was completed)
    completion_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Financial amounts (from the invoice/quote at completion time)
    gross_amount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    discount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    tax: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    net_amount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)

    # Currency (ISO 4217)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # Payment status (synced from invoice)
    payment_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unpaid"
    )  # InvoicePaymentStatus enum value

    # Entry type — primary or adjustment/reversal
    is_primary: Mapped[bool] = mapped_column(default=True, nullable=False)

    # For adjustments/reversals: reference to the original entry
    adjusts_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_ledger_entries.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Immutable transaction reference
    transaction_reference: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)

    # FIELDed commercial-policy fee evidence at ledger entry time.
    fee_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    service_execution: Mapped[ServiceExecution] = relationship(
        back_populates="ledger_entries", foreign_keys=[service_execution_id]
    )
    invoice: Mapped[Invoice | None] = relationship(foreign_keys=[invoice_id])
    service_offer: Mapped[ServiceOffer] = relationship(foreign_keys=[service_offer_id])
    adjusts_entry: Mapped[ServiceLedgerEntry | None] = relationship(
        foreign_keys=[adjusts_entry_id], remote_side="ServiceLedgerEntry.id"
    )
