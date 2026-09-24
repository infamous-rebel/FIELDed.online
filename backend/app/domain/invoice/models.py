"""Invoice domain model.

An Invoice represents a financial document issued by a business to a
customer for a completed service.  It is linked to the ServiceExecution,
Booking, and Quote that produced it.

Invoice amounts derive from persisted transaction/pricing data.
Totals are deterministically reproducible from persisted line items.

No LLM is used to calculate invoice totals.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.common.base_model import BaseModel

if TYPE_CHECKING:
    from app.domain.identity.models import Business, User
    from app.domain.quote.models import Quote
    from app.domain.service_execution.models import ServiceExecution


class Invoice(BaseModel):
    """A financial invoice for a completed service.

    Linked to the actual transaction:
        Business -> Customer -> ServiceExecution -> Booking -> Quote
    """

    __tablename__ = "invoices"
    __table_args__ = (
        # Invoice number must be unique within a business scope
        UniqueConstraint("business_id", "invoice_number", name="uq_invoice_business_number"),
        Index("ix_invoices_business_id", "business_id"),
        Index("ix_invoices_customer_id", "customer_id"),
        Index("ix_invoices_service_execution_id", "service_execution_id"),
        Index("ix_invoices_booking_id", "booking_id"),
        Index("ix_invoices_payment_status", "payment_status"),
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
        unique=True,  # One primary invoice per execution
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

    # Invoice identification
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Dates
    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Currency (ISO 4217)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # Financial totals — derived from line items
    subtotal: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    discount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    tax: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    total: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")

    # Payment tracking
    payment_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unpaid"
    )  # InvoicePaymentStatus enum value

    # Invoice lifecycle
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")  # InvoiceStatus enum value

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    business: Mapped[Business] = relationship(foreign_keys=[business_id])
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
    service_execution: Mapped[ServiceExecution] = relationship(
        back_populates="invoices", foreign_keys=[service_execution_id]
    )
    booking: Mapped[Booking] = relationship(foreign_keys=[booking_id])  # noqa: F821
    quote: Mapped[Quote | None] = relationship(foreign_keys=[quote_id])
    line_items: Mapped[list[InvoiceLineItem]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLineItem(BaseModel):
    """A line item within an invoice.

    The invoice total must be deterministically reproducible from
    its persisted lines and financial fields.
    """

    __tablename__ = "invoice_line_items"
    __table_args__ = (Index("ix_invoice_line_items_invoice_id", "invoice_id"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Line item details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    service_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Quantity and pricing
    quantity: Mapped[str] = mapped_column(Numeric(precision=10, scale=2), nullable=False, default="1.00")
    unit_price: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)

    # Line-level adjustments
    discount: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")
    tax: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default="0.00")

    # Line total (deterministic: quantity * unit_price - discount + tax)
    line_total: Mapped[str] = mapped_column(Numeric(precision=12, scale=2), nullable=False)

    # Currency
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # Sort order
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    # Relationships
    invoice: Mapped[Invoice] = relationship(back_populates="line_items")
