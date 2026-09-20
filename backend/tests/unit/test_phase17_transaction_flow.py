"""Phase 17 — Transaction flow unit tests.

Tests cover the deterministic completion cascade and payment validation:
- Service execution completion cascades to booking COMPLETED
- Booking COMPLETED cascades to enquiry COMPLETED
- Payment amount validation against invoice
- Payment amount mismatch → rejected
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.payment.stub import StubPaymentProvider
from app.domain.booking.models import Booking
from app.domain.booking.repository import BookingRepository
from app.domain.booking.service import BookingService
from app.domain.common.enums import (
    BookingStatus,
    EnquiryStatus,
    InvoiceStatus,
    PaymentStatus,
)
from app.domain.enquiry.models import Enquiry
from app.domain.enquiry.repository import EnquiryRepository
from app.domain.invoice.models import Invoice, InvoiceLineItem
from app.domain.invoice.repository import InvoiceRepository
from app.domain.payment.service import PaymentService
from app.domain.quote.models import Quote
from app.domain.service_execution.models import ServiceExecution
from app.domain.service_execution.service import ServiceExecutionService
from app.domain.services.models import ServiceOffer
from app.exceptions import ValidationError
from tests.factories import (
    business_factory,
    business_member_factory,
    business_profile_factory,
    customer_profile_factory,
    service_category_factory,
    user_factory,
)


async def _make_user(db_session: AsyncSession, prefix: str):
    user = user_factory(email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com")
    db_session.add(user)
    await db_session.flush()
    db_session.add(customer_profile_factory(user_id=user.id))
    await db_session.flush()
    return user


async def _make_chain(
    db_session: AsyncSession,
    *,
    customer,
    owner,
    enquiry_status: str = "booked",
    booking_status=BookingStatus.CONFIRMED,
):
    """Create enquiry → quote → booking (confirmed by default)."""
    biz = business_factory()
    db_session.add(biz)
    await db_session.flush()

    db_session.add(business_member_factory(user_id=owner.id, business_id=biz.id, role="owner"))
    db_session.add(business_profile_factory(business_id=biz.id))
    await db_session.flush()

    category = service_category_factory()
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name=f"Flow Svc {uuid.uuid4().hex[:6]}",
        slug=f"flow-svc-{uuid.uuid4().hex[:6]}",
        pricing_model="fixed",
        delivery_mode="on_site",
        status="active",
    )
    db_session.add(offer)
    await db_session.flush()

    enquiry = Enquiry(
        reference=f"ENQ-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        business_id=biz.id,
        service_offer_id=offer.id,
        subject="Flow test",
        message="Testing completion cascade",
        status=enquiry_status,
    )
    db_session.add(enquiry)
    await db_session.flush()

    quote = Quote(
        reference=f"QUO-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        business_id=biz.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        amount="150.00",
        currency="GBP",
        status="accepted",
    )
    db_session.add(quote)
    await db_session.flush()

    booking = Booking(
        reference=f"BKG-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        business_id=biz.id,
        quote_id=quote.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        requested_at=datetime.now(UTC) + timedelta(days=1),
        currency="GBP",
        status=booking_status,
    )
    db_session.add(booking)
    await db_session.flush()

    return biz, enquiry, quote, booking


async def _make_paid_invoice(db_session: AsyncSession, *, customer, owner, biz, booking) -> Invoice:
    """Create a completed execution + issued invoice for the booking."""
    execution = ServiceExecution(
        business_id=biz.id,
        customer_id=customer.id,
        booking_id=booking.id,
        service_offer_id=booking.service_offer_id,
        quote_id=booking.quote_id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=owner.id,
    )
    db_session.add(execution)
    await db_session.flush()

    invoice = Invoice(
        business_id=biz.id,
        customer_id=customer.id,
        service_execution_id=execution.id,
        booking_id=booking.id,
        quote_id=booking.quote_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
        issue_date=datetime.now(UTC),
        currency="GBP",
        subtotal="150.00",
        discount="0.00",
        tax="0.00",
        total="150.00",
        payment_status="unpaid",
        status=InvoiceStatus.ISSUED,
    )
    db_session.add(invoice)
    await db_session.flush()

    db_session.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            description="Service delivery",
            quantity="1.00",
            unit_price="150.00",
            discount="0.00",
            tax="0.00",
            line_total="150.00",
            currency="GBP",
            sort_order=0,
        )
    )
    await db_session.flush()
    return invoice


@pytest_asyncio.fixture
async def customer(db_session: AsyncSession):
    return await _make_user(db_session, "cust")


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession):
    return await _make_user(db_session, "owner")


class TestCompletionCascade:
    """Execution completion deterministically cascades up the chain."""

    @pytest.mark.asyncio
    async def test_execution_completion_cascades_to_booking_completed(
        self, db_session: AsyncSession, customer, owner
    ):
        biz, enquiry, quote, booking = await _make_chain(db_session, customer=customer, owner=owner)

        # Production flow: the confirmed booking moves to in_progress
        # before the service is completed (CONFIRMED → COMPLETED is not
        # a valid booking transition).
        booking_service = BookingService(db_session)
        booking = await booking_service.transition_booking(
            booking, BookingStatus.IN_PROGRESS, actor="business"
        )

        service = ServiceExecutionService(db_session)
        execution = await service.create_from_booking(booking_id=booking.id, business_id=biz.id)
        execution = await service.start_service(execution, actor_id=owner.id)
        execution = await service.complete_service(execution, actor_id=owner.id)

        assert execution.status == "completed"

        booking_repo = BookingRepository(db_session)
        refreshed = await booking_repo.get_by_id(booking.id)
        assert refreshed.status == BookingStatus.COMPLETED

        # Completion records exist (invoice created atomically)
        invoice_repo = InvoiceRepository(db_session)
        invoice = await invoice_repo.get_by_service_execution_id(execution.id)
        assert invoice is not None

    @pytest.mark.asyncio
    async def test_booking_completion_cascades_to_enquiry_completed(
        self, db_session: AsyncSession, customer, owner
    ):
        _, enquiry, _, booking = await _make_chain(
            db_session, customer=customer, owner=owner, enquiry_status="booked"
        )
        assert enquiry.status == EnquiryStatus.BOOKED

        service = BookingService(db_session)
        await service.transition_booking(booking, BookingStatus.IN_PROGRESS, actor="business")
        await service.transition_booking(booking, BookingStatus.COMPLETED, actor="business")

        enquiry_repo = EnquiryRepository(db_session)
        refreshed = await enquiry_repo.get_by_id(enquiry.id)
        assert refreshed.status == EnquiryStatus.COMPLETED


class TestPaymentValidation:
    """Payment amounts are validated deterministically against the invoice."""

    @pytest.mark.asyncio
    async def test_payment_amount_validated_against_invoice(
        self, db_session: AsyncSession, customer, owner
    ):
        biz, _, _, booking = await _make_chain(db_session, customer=customer, owner=owner)
        invoice = await _make_paid_invoice(
            db_session, customer=customer, owner=owner, biz=biz, booking=booking
        )

        service = PaymentService(db_session, payment_provider=StubPaymentProvider())
        payment = await service.create_payment(
            business_id=biz.id,
            customer_id=customer.id,
            invoice_id=invoice.id,
            amount="100.00",
            currency="GBP",
            payment_method="card",
            idempotency_key=f"pay-{uuid.uuid4().hex[:12]}",
        )
        payment = await service.process_payment(payment)

        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.invoice_id == invoice.id

        # Remaining outstanding balance can still be paid (partial support)
        second = await service.create_payment(
            business_id=biz.id,
            customer_id=customer.id,
            invoice_id=invoice.id,
            amount="50.00",
            currency="GBP",
            payment_method="card",
            idempotency_key=f"pay-{uuid.uuid4().hex[:12]}",
        )
        assert second.status == PaymentStatus.PENDING

    @pytest.mark.asyncio
    async def test_payment_amount_mismatch_rejected(
        self, db_session: AsyncSession, customer, owner
    ):
        biz, _, _, booking = await _make_chain(db_session, customer=customer, owner=owner)
        invoice = await _make_paid_invoice(
            db_session, customer=customer, owner=owner, biz=biz, booking=booking
        )

        service = PaymentService(db_session, payment_provider=StubPaymentProvider())

        # Overpayment beyond the outstanding balance is rejected
        with pytest.raises(ValidationError, match="exceeds outstanding"):
            await service.create_payment(
                business_id=biz.id,
                customer_id=customer.id,
                invoice_id=invoice.id,
                amount="999.00",
                currency="GBP",
                payment_method="card",
                idempotency_key=f"pay-{uuid.uuid4().hex[:12]}",
            )

        # Currency mismatch is rejected
        with pytest.raises(ValidationError, match="currency"):
            await service.create_payment(
                business_id=biz.id,
                customer_id=customer.id,
                invoice_id=invoice.id,
                amount="150.00",
                currency="USD",
                payment_method="card",
                idempotency_key=f"pay-{uuid.uuid4().hex[:12]}",
            )
