"""Booking API endpoints.

Provides booking creation (customer from accepted quote), listing,
retrieval, lifecycle transitions, and availability checks.

All ownership is verified server-side.

Bulk operations (RG-007): batch transition and CSV export for bookings.
"""

from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import ProviderFactory
from app.database import get_db_session
from app.domain.booking.schemas import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    BookingCreate,
    BookingRead,
    BookingTransitionRequest,
)
from app.domain.booking.service import BookingService
from app.domain.common.enums import BookingStatus
from app.domain.identity.models import User
from app.domain.invoice.repository import InvoiceRepository
from app.domain.payment.models import Payment
from app.domain.payment.schemas import PaymentRead
from app.domain.payment.service import PaymentService
from app.domain.service_execution.repository import ServiceExecutionRepository
from app.exceptions import NotFoundError, ValidationError
from app.security.authorization import require_business_member, require_customer

router = APIRouter()


class CustomerPayRequest(BaseModel):
    """Request schema for customer payment against a booking."""

    payment_method: str = Field("card", description="Payment method type")
    idempotency_key: str = Field(..., description="Client-generated idempotency key")


def _booking_to_read(booking) -> BookingRead:
    """Convert a Booking model to the read schema."""
    return BookingRead.model_validate(booking)


# --- Business endpoints ---


@router.get(
    "/{business_id}/bookings",
    response_model=list[BookingRead],
)
async def list_business_bookings(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[BookingRead]:
    """List bookings for a business."""
    service = BookingService(db)
    bookings = await service.list_business_bookings(business_id, status=status, limit=limit, offset=offset)
    return [_booking_to_read(b) for b in bookings]


@router.get(
    "/{business_id}/bookings/{booking_id}",
    response_model=BookingRead,
)
async def get_business_booking(
    business_id: uuid.UUID,
    booking_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BookingRead:
    """Get a specific booking for a business."""
    service = BookingService(db)
    booking = await service.get_business_booking(booking_id, business_id)
    return _booking_to_read(booking)


@router.post(
    "/{business_id}/bookings/{booking_id}/transition",
    response_model=BookingRead,
)
async def transition_business_booking(
    business_id: uuid.UUID,
    booking_id: uuid.UUID,
    body: BookingTransitionRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BookingRead:
    """Transition a booking (business actions)."""
    service = BookingService(db)
    booking = await service.get_business_booking(booking_id, business_id)
    target_status = BookingStatus(body.target_status)
    booking = await service.transition_booking(booking, target_status, actor="business")
    await db.refresh(booking)
    return _booking_to_read(booking)


@router.post(
    "/{business_id}/availability",
    response_model=AvailabilityCheckResponse,
)
async def check_availability(
    business_id: uuid.UUID,
    body: AvailabilityCheckRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AvailabilityCheckResponse:
    """Check availability for a proposed booking time."""
    service = BookingService(db)
    result = await service.check_availability(
        business_id=business_id,
        service_offer_id=body.service_offer_id,
        requested_at=body.requested_at,
    )
    return AvailabilityCheckResponse(
        available=result.available,
        requested_at=result.requested_at,
        reason=result.reason,
        brain_version_id=result.brain_version_id,
        matched_rules=result.matched_rules,
        blocked_by=result.blocked_by,
    )


# --- Bulk operations (RG-007) ---


class BulkBookingTransitionRequest(BaseModel):
    """Request body for bulk transitioning multiple bookings."""

    booking_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    target_status: str


class BulkBookingTransitionResult(BaseModel):
    """Result of a bulk booking transition operation."""

    succeeded: list[uuid.UUID] = []
    failed: list[dict] = []
    total: int = 0


@router.post(
    "/{business_id}/bookings/bulk-transition",
    response_model=BulkBookingTransitionResult,
)
async def bulk_transition_bookings(
    business_id: uuid.UUID,
    body: BulkBookingTransitionRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BulkBookingTransitionResult:
    """Bulk transition multiple bookings to a target status.

    Each booking is transitioned independently — failures do not
    roll back successes. Returns lists of succeeded/failed IDs.
    """
    service = BookingService(db)
    target_status = BookingStatus(body.target_status)

    result = BulkBookingTransitionResult(total=len(body.booking_ids))

    for booking_id in body.booking_ids:
        try:
            booking = await service.get_business_booking(booking_id, business_id)
            booking = await service.transition_booking(booking, target_status, actor="business")
            await db.refresh(booking)
            result.succeeded.append(booking_id)
        except Exception as exc:
            result.failed.append({"id": str(booking_id), "reason": str(exc)})

    return result


@router.get(
    "/{business_id}/bookings/export/csv",
)
async def export_bookings_csv(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
) -> Response:
    """Export business bookings as CSV.

    Returns a CSV file with booking ID, customer ID, status,
    requested_at, created_at.
    """
    service = BookingService(db)
    bookings = await service.list_business_bookings(business_id, status=status, limit=10000, offset=0)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["booking_id", "customer_id", "status", "requested_at", "created_at"])

    for b in bookings:
        writer.writerow(
            [
                str(b.id),
                str(b.customer_id),
                b.status,
                b.requested_at.isoformat() if b.requested_at else "",
                b.created_at.isoformat() if b.created_at else "",
            ]
        )

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bookings-{business_id}.csv"},
    )


# --- Customer endpoints ---


@router.post("/my-bookings", response_model=BookingRead, status_code=201)
async def create_booking(
    body: BookingCreate,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BookingRead:
    """Create a booking from an accepted quote (customer action).

    The booking is subject to Brain availability evaluation.
    """
    service = BookingService(db)
    booking = await service.create_booking(
        customer_id=user.id,
        quote_id=body.quote_id,
        requested_at=body.requested_at,
        notes=body.notes,
    )
    await db.refresh(booking)
    return _booking_to_read(booking)


@router.get("/my-bookings", response_model=list[BookingRead])
async def list_my_bookings(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[BookingRead]:
    """List all bookings for the authenticated customer."""
    service = BookingService(db)
    bookings = await service.list_customer_bookings(user.id, status=status, limit=limit, offset=offset)
    return [_booking_to_read(b) for b in bookings]


@router.get("/my-bookings/{booking_id}", response_model=BookingRead)
async def get_my_booking(
    booking_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BookingRead:
    """Get a specific booking owned by the authenticated customer."""
    service = BookingService(db)
    booking = await service.get_customer_booking(booking_id, user.id)
    return _booking_to_read(booking)


@router.post("/my-bookings/{booking_id}/transition", response_model=BookingRead)
async def transition_my_booking(
    booking_id: uuid.UUID,
    body: BookingTransitionRequest,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BookingRead:
    """Transition a booking (customer: cancel only)."""
    service = BookingService(db)
    booking = await service.get_customer_booking(booking_id, user.id)
    target_status = BookingStatus(body.target_status)
    booking = await service.transition_booking(booking, target_status, actor="customer")
    await db.refresh(booking)
    return _booking_to_read(booking)


@router.post("/my-bookings/{booking_id}/pay", response_model=PaymentRead, status_code=201)
async def pay_my_booking(
    booking_id: uuid.UUID,
    request: Request,
    body: CustomerPayRequest,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentRead:
    """Pay for a completed booking's invoice (customer action).

    Lifecycle: booking -> service execution -> completion -> invoice -> payment.
    The service must be completed before payment is possible.
    The payment provider is resolved from application configuration
    via ProviderFactory — never hardcoded.
    """
    # 1. Verify customer owns the booking
    booking_service = BookingService(db)
    booking = await booking_service.get_customer_booking(booking_id, user.id)

    # 2. Find the booking's service execution
    execution_repo = ServiceExecutionRepository(db)
    execution = await execution_repo.get_by_booking_id(booking.id)
    if execution is None:
        raise NotFoundError("Service execution not found — service must be scheduled first")

    # 3. Find the invoice for the execution (created at completion)
    invoice_repo = InvoiceRepository(db)
    invoice = await invoice_repo.get_by_service_execution_id(execution.id)
    if invoice is None:
        raise ValidationError("Payment not yet available — service must be completed first")

    # 4. Resolve the configured payment provider (never hardcoded)
    factory = ProviderFactory.from_settings(request.app.state.settings)
    provider = factory.payment_provider
    payment_service = PaymentService(db, payment_provider=provider)

    payment = await payment_service.create_payment(
        business_id=booking.business_id,
        customer_id=user.id,
        invoice_id=invoice.id,
        amount=str(invoice.total),
        currency=invoice.currency,
        payment_method=body.payment_method,
        idempotency_key=body.idempotency_key,
        provider_name=provider.provider_name,
        actor_id=user.id,
    )

    # 5. Process via the configured provider
    payment = await payment_service.process_payment(payment)

    # Reload with attempts eager-loaded (PaymentRead requires it;
    # lazy access after commit would raise MissingGreenlet)
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db.execute(select(Payment).where(Payment.id == payment.id).options(selectinload(Payment.attempts)))
    payment = result.scalar_one()
    return PaymentRead.model_validate(payment)
