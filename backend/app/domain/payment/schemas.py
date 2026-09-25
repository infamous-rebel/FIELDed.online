"""Payment Pydantic schemas.

Request/response schemas for the Payment API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, computed_field

# Allow Decimal or str to be serialized as str
StrOrDecimal = Annotated[str, BeforeValidator(lambda v: str(v))]


class PaymentAttemptRead(BaseModel):
    """Read schema for a payment attempt."""

    id: uuid.UUID
    payment_id: uuid.UUID
    attempt_number: int
    provider: str
    provider_reference: str | None = None
    status: str
    amount: StrOrDecimal
    currency: str
    requested_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    provider_response: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentRead(BaseModel):
    """Read schema for a payment."""

    id: uuid.UUID
    idempotency_key: str
    business_id: uuid.UUID
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    amount: StrOrDecimal
    currency: str
    payment_method: str
    status: str
    provider: str
    provider_reference: str | None = None
    refunded_amount: StrOrDecimal
    refund_provider_reference: str | None = None
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    expires_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    notes: str | None = None
    attempts: list[PaymentAttemptRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field(return_type=str | None)
    @property
    def client_secret(self) -> str | None:
        """Extract the Stripe client_secret for frontend confirmation.

        Sourced from the latest attempt's provider_response when the
        payment is not yet confirmed.  Returns None when no client
        secret is available (e.g. stub provider or already confirmed).
        """
        attempts_data = self.attempts if hasattr(self, "attempts") else []
        for attempt in reversed(attempts_data):
            pr = attempt.provider_response if hasattr(attempt, "provider_response") else None
            if isinstance(pr, dict):
                cs = pr.get("client_secret")
                if cs:
                    return cs
        return None

    @computed_field(return_type=bool)
    @property
    def confirmation_required(self) -> bool:
        """Whether the payment requires frontend Stripe confirmation.

        True when the payment is in 'processing' state AND a client
        secret is available.  False for synchronous providers (stub)
        or already-confirmed payments.
        """
        return self.status == "processing" and self.client_secret is not None


class PaymentCreateRequest(BaseModel):
    """Request schema for creating a payment."""

    invoice_id: uuid.UUID = Field(..., description="Invoice to pay against")
    amount: str = Field(..., description="Payment amount (decimal string)")
    currency: str = Field("GBP", description="ISO 4217 currency code")
    payment_method: str = Field("card", description="Payment method type")
    idempotency_key: str = Field(..., description="Client-generated idempotency key")
    notes: str | None = None


class PaymentRefundRequest(BaseModel):
    """Request schema for refunding a payment."""

    amount: str | None = Field(None, description="Refund amount (null = full refund)")
    reason: str | None = Field(None, description="Reason for refund")


class PaymentListRead(BaseModel):
    """List wrapper for payments."""

    items: list[PaymentRead]
    total: int | None = None


class InvoicePaymentStatusRead(BaseModel):
    """Invoice payment status with balance information."""

    invoice_id: uuid.UUID
    invoice_number: str
    total: StrOrDecimal
    currency: str
    paid_amount: StrOrDecimal
    outstanding_amount: StrOrDecimal
    payment_status: str
    payments: list[PaymentRead] = []
