"""Invoice Pydantic schemas.

Request/response schemas for the Invoice API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, BeforeValidator
from pydantic.fields import Field
from typing_extensions import Annotated


# Allow Decimal or str to be serialized as str
StrOrDecimal = Annotated[str, BeforeValidator(lambda v: str(v))]


class InvoiceLineItemRead(BaseModel):
    """Read schema for an invoice line item."""

    id: uuid.UUID
    invoice_id: uuid.UUID
    description: str
    service_reference: str | None = None
    quantity: StrOrDecimal
    unit_price: StrOrDecimal
    discount: StrOrDecimal
    tax: StrOrDecimal
    line_total: StrOrDecimal
    currency: str
    sort_order: int

    model_config = {"from_attributes": True}


class InvoiceRead(BaseModel):
    """Read schema for an invoice."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    service_execution_id: uuid.UUID
    booking_id: uuid.UUID
    quote_id: uuid.UUID | None = None
    invoice_number: str
    issue_date: datetime
    due_date: datetime | None = None
    currency: str
    subtotal: StrOrDecimal
    discount: StrOrDecimal
    tax: StrOrDecimal
    total: StrOrDecimal
    payment_status: str
    status: str
    notes: str | None = None
    line_items: list[InvoiceLineItemRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoicePaymentUpdateRequest(BaseModel):
    """Request schema for updating invoice payment status."""

    payment_status: str = Field(..., description="New payment status (unpaid, partially_paid, paid, void)")
    notes: str | None = None


class InvoiceListRead(BaseModel):
    """List wrapper for invoices."""

    items: list[InvoiceRead]
    total: int | None = None
