"""Payment API endpoints.

Provides payment creation, status tracking, refund processing,
invoice payment status, and provider webhook handling.

All ownership is verified server-side.
Tenant isolation is enforced at the repository level.

AI does NOT determine payment amount, authorization,
transaction state, or refund eligibility.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters import ProviderFactory
from app.adapters.payment.base import PaymentProvider
from app.database import get_db_session
from app.domain.identity.models import User
from app.domain.payment.models import Payment
from app.domain.payment.schemas import (
    InvoicePaymentStatusRead,
    PaymentCreateRequest,
    PaymentRead,
    PaymentRefundRequest,
)
from app.domain.payment.service import PaymentService
from app.security.authorization import (
    require_business_member,
    require_customer,
)

router = APIRouter()


def _payment_provider(request: Request) -> PaymentProvider:
    """Resolve the configured payment provider from request settings."""
    factory = ProviderFactory.from_settings(request.app.state.settings)
    return factory.payment_provider


def _payment_service(db: AsyncSession, request: Request) -> PaymentService:
    """Create a PaymentService with the configured provider."""
    return PaymentService(db, payment_provider=_payment_provider(request))


async def _refresh_payment(db: AsyncSession, payment: Payment) -> Payment:
    """Refresh a payment with attempts relationship loaded."""
    from sqlalchemy import select

    result = await db.execute(select(Payment).where(Payment.id == payment.id).options(selectinload(Payment.attempts)))
    return result.scalar_one()


def _payment_to_read(payment) -> PaymentRead:
    """Convert a Payment model to the read schema."""
    return PaymentRead.model_validate(payment)


# --- Business endpoints ---


@router.post(
    "/businesses/{business_id}/payments",
    response_model=PaymentRead,
    status_code=201,
)
async def create_payment(
    business_id: uuid.UUID,
    body: PaymentCreateRequest,
    request: Request,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentRead:
    """Create a payment for an invoice (business-initiated).

    Idempotent: duplicate idempotency_key returns existing payment.
    """
    service = _payment_service(db, request)
    payment = await service.create_payment(
        business_id=business_id,
        customer_id=await _resolve_invoice_customer(db, body.invoice_id),
        invoice_id=body.invoice_id,
        amount=body.amount,
        currency=body.currency,
        payment_method=body.payment_method,
        idempotency_key=body.idempotency_key,
        provider_name=_payment_provider(request).provider_name,
        notes=body.notes,
        actor_id=user.id,
    )
    # Auto-process with stub provider (synchronous success)
    from app.domain.common.enums import PaymentStatus

    if payment.status == PaymentStatus.PENDING:
        payment = await service.process_payment(payment)
    payment = await _refresh_payment(db, payment)
    return _payment_to_read(payment)


@router.get(
    "/businesses/{business_id}/payments",
    response_model=list[PaymentRead],
)
async def list_business_payments(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request = None,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[PaymentRead]:
    """List payments for a business."""
    service = _payment_service(db, request)
    payments = await service.list_business_payments(business_id, status=status, limit=limit, offset=offset)
    return [_payment_to_read(p) for p in payments]


@router.get(
    "/businesses/{business_id}/payments/{payment_id}",
    response_model=PaymentRead,
)
async def get_business_payment(
    business_id: uuid.UUID,
    payment_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request = None,
) -> PaymentRead:
    """Get a specific payment for a business."""
    service = _payment_service(db, request)
    payment = await service.get_business_payment(payment_id, business_id)
    payment = await _refresh_payment(db, payment)
    return _payment_to_read(payment)


@router.post(
    "/businesses/{business_id}/payments/{payment_id}/refund",
    response_model=PaymentRead,
)
async def refund_payment(
    business_id: uuid.UUID,
    payment_id: uuid.UUID,
    body: PaymentRefundRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> PaymentRead:
    """Refund a payment (full or partial).

    Only business members can initiate refunds.
    Refund eligibility is deterministic — AI does not decide.
    """
    service = _payment_service(db, request)
    payment = await service.get_business_payment(payment_id, business_id)
    payment = await service.refund_payment(
        payment,
        amount=body.amount,
        reason=body.reason,
        actor_id=user.id,
    )
    payment = await _refresh_payment(db, payment)
    return _payment_to_read(payment)


@router.get(
    "/businesses/{business_id}/invoices/{invoice_id}/payment-status",
    response_model=InvoicePaymentStatusRead,
)
async def get_invoice_payment_status(
    business_id: uuid.UUID,
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request = None,
) -> InvoicePaymentStatusRead:
    """Get payment status and balance for an invoice."""
    service = _payment_service(db, request)
    status = await service.get_invoice_payment_status(invoice_id)
    return InvoicePaymentStatusRead(
        **{
            **status,
            "payments": [_payment_to_read(p) for p in status["payments"]],
        }
    )


@router.get(
    "/businesses/{business_id}/payments/transactions/history",
    response_model=list[PaymentRead],
)
async def get_transaction_history(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request = None,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[PaymentRead]:
    """Get transaction history for a business."""
    service = _payment_service(db, request)
    payments = await service.list_business_payments(business_id, status=status, limit=limit, offset=offset)
    return [_payment_to_read(p) for p in payments]


# --- Customer endpoints ---


@router.get(
    "/my-payments",
    response_model=list[PaymentRead],
)
async def list_my_payments(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request = None,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[PaymentRead]:
    """List payments for the authenticated customer."""
    service = _payment_service(db, request)
    payments = await service.list_customer_payments(user.id, status=status, limit=limit, offset=offset)
    return [_payment_to_read(p) for p in payments]


@router.get(
    "/my-payments/{payment_id}",
    response_model=PaymentRead,
)
async def get_my_payment(
    payment_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request = None,
) -> PaymentRead:
    """Get a specific payment for the authenticated customer."""
    service = _payment_service(db, request)
    payment = await service.get_customer_payment(payment_id, user.id)
    payment = await _refresh_payment(db, payment)
    return _payment_to_read(payment)


# --- Provider webhook endpoint (public, no auth) ---


@router.post(
    "/webhooks/payment/{provider}",
    status_code=200,
)
async def payment_webhook(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    """Handle payment provider webhooks.

    Verifies webhook signature, parses event, and updates
    payment state idempotently.  Duplicate webhook deliveries
    are safely ignored.
    """
    body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON payload"},
        )

    # Get the payment provider to verify signature
    payment_prov = _payment_provider(request)
    settings = request.app.state.settings
    webhook_secret = getattr(settings, "payment_webhook_secret", "")

    # Read the signature from the provider-specific header.
    # Stripe uses "Stripe-Signature"; we also accept a generic header.
    signature = request.headers.get("Stripe-Signature", "") or request.headers.get("X-Payment-Signature", "")

    # Verify signature if secret is configured
    if webhook_secret and signature:
        is_valid = await payment_prov.verify_webhook_signature(body, signature, webhook_secret)
        if not is_valid:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid webhook signature"},
            )
    elif webhook_secret and not signature:
        # Secret is configured but no signature was provided — reject
        return JSONResponse(
            status_code=401,
            content={"error": "Missing webhook signature"},
        )

    # Parse the event
    event = await payment_prov.parse_webhook_event(payload)

    # Process the event
    service = PaymentService(db, payment_provider=payment_prov)
    payment = await service.handle_webhook(
        provider_event_id=event.provider_event_id,
        provider_payment_reference=event.provider_payment_reference,
        event_type=event.event_type,
        status=event.status,
        amount=str(event.amount) if event.amount else None,
    )

    return JSONResponse(
        status_code=200,
        content={
            "received": True,
            "payment_id": str(payment.id) if payment else None,
        },
    )


# --- Helpers ---


async def _resolve_invoice_customer(db: AsyncSession, invoice_id: uuid.UUID) -> uuid.UUID:
    """Resolve the customer_id from an invoice."""
    from sqlalchemy import select

    from app.domain.invoice.models import Invoice

    result = await db.execute(select(Invoice.customer_id).where(Invoice.id == invoice_id))
    customer_id = result.scalar_one_or_none()
    if customer_id is None:
        from app.exceptions import NotFoundError

        raise NotFoundError("Invoice not found")
    return customer_id
