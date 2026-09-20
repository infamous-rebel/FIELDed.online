"""Service Ledger Pydantic schemas.

Request/response schemas for the Ledger API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator

# Allow Decimal or str to be serialized as str
StrOrDecimal = Annotated[str, BeforeValidator(lambda v: str(v))]


class LedgerEntryRead(BaseModel):
    """Read schema for a ledger entry."""

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    service_execution_id: uuid.UUID
    booking_id: uuid.UUID
    quote_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None
    service_offer_id: uuid.UUID
    completion_date: datetime
    gross_amount: StrOrDecimal
    discount: StrOrDecimal
    tax: StrOrDecimal
    net_amount: StrOrDecimal
    currency: str
    payment_status: str
    is_primary: bool
    adjusts_entry_id: uuid.UUID | None = None
    transaction_reference: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LedgerSummaryRead(BaseModel):
    """Read schema for ledger summary/totals."""

    total_entries: int
    total_gross: StrOrDecimal
    total_discount: StrOrDecimal
    total_tax: StrOrDecimal
    total_net: StrOrDecimal
    paid_amount: StrOrDecimal
    outstanding_amount: StrOrDecimal


class LedgerAdjustmentRequest(BaseModel):
    """Request schema for creating a ledger adjustment."""

    adjustment_gross: str
    adjustment_discount: str = "0.00"
    adjustment_tax: str = "0.00"
    adjustment_net: str
    currency: str = "GBP"
    notes: str


class LedgerExportParams(BaseModel):
    """Query parameters for ledger export."""

    payment_status: str | None = None
    service_offer_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
