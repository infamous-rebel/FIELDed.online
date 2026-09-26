"""Phase 13 — Service Execution, Invoice, Ledger tests.

Tests cover:
- Service execution lifecycle and state transitions
- Completion idempotency (no duplicate invoices/ledger entries)
- Invoice creation with deterministic totals
- Ledger entry creation and integrity
- Authorization and tenant isolation
- PDF generation
- API endpoints
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.common.enums import (
    SERVICE_EXECUTION_TRANSITIONS,
    BookingStatus,
    InvoicePaymentStatus,
    InvoiceStatus,
    ServiceExecutionStatus,
)
from app.domain.identity.models import (
    CustomerProfile,
    User,
)
from app.domain.invoice.models import Invoice, InvoiceLineItem
from app.domain.invoice.service import InvoiceService
from app.domain.ledger.models import ServiceLedgerEntry
from app.domain.ledger.service import LedgerService
from app.domain.quote.models import Quote
from app.domain.service_execution.service import ServiceExecutionService
from app.domain.services.models import ServiceOffer
from app.exceptions import (
    AuthorizationError,
    ConflictError,
    StateTransitionError,
    ValidationError,
)
from app.security.password import hash_password
from tests.factories import (
    business_factory,
    business_member_factory,
    service_category_factory,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def business_owner(db_session: AsyncSession) -> User:
    """Create a user who owns a business."""
    from app.domain.identity.models import User

    user = User(
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()

    profile = CustomerProfile(user_id=user.id, first_name="Biz", last_name="Owner")
    db_session.add(profile)
    await db_session.flush()

    biz = business_factory()
    db_session.add(biz)
    await db_session.flush()

    member = business_member_factory(user_id=user.id, business_id=biz.id, role="owner")
    db_session.add(member)
    await db_session.flush()

    await db_session.refresh(user, attribute_names=["customer_profile", "business_memberships"])
    user._business = biz
    return user


@pytest_asyncio.fixture
async def confirmed_booking(
    db_session: AsyncSession,
    test_user: User,
    business_owner: User,
) -> Booking:
    """Create a confirmed booking for testing."""
    biz = business_owner._business

    # Create service category and offer
    category = service_category_factory()
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name=f"Test Service {uuid.uuid4().hex[:6]}",
        slug=f"test-svc-{uuid.uuid4().hex[:6]}",
        pricing_model="fixed",
        delivery_mode="on_site",
        status="active",
    )
    db_session.add(offer)
    await db_session.flush()

    # Create enquiry
    from app.domain.enquiry.models import Enquiry

    enquiry = Enquiry(
        reference=f"ENQ-{uuid.uuid4().hex[:8]}",
        customer_id=test_user.id,
        business_id=biz.id,
        service_offer_id=offer.id,
        subject="Test enquiry",
        message="I need this service",
        status="quoted",
    )
    db_session.add(enquiry)
    await db_session.flush()

    # Create quote
    quote = Quote(
        reference=f"QUO-{uuid.uuid4().hex[:8]}",
        customer_id=test_user.id,
        business_id=biz.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        amount="150.00",
        currency="GBP",
        status="accepted",
    )
    db_session.add(quote)
    await db_session.flush()

    # Create booking
    booking = Booking(
        reference=f"BKG-{uuid.uuid4().hex[:8]}",
        customer_id=test_user.id,
        business_id=biz.id,
        quote_id=quote.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        requested_at=datetime.now(UTC) + timedelta(days=1),
        currency="GBP",
        status=BookingStatus.CONFIRMED,
    )
    db_session.add(booking)
    await db_session.flush()

    return booking


# ─── Service Execution Tests ────────────────────────────────────────────────


class TestServiceExecutionLifecycle:
    """Test service execution state machine."""

    async def test_create_from_confirmed_booking(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """A service execution can be created from a confirmed booking."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        assert execution.status == ServiceExecutionStatus.IN_PROGRESS
        assert execution.started_at is not None
        assert execution.booking_id == confirmed_booking.id
        assert execution.business_id == biz.id
        assert execution.customer_id == confirmed_booking.customer_id

    async def test_cannot_create_from_unconfirmed_booking(self, db_session: AsyncSession, business_owner: User):
        """Cannot create execution from a non-confirmed booking."""
        biz = business_owner._business

        # Create a booking in REQUESTED status
        from app.domain.enquiry.models import Enquiry
        from app.domain.services.models import ServiceOffer

        category = service_category_factory()
        db_session.add(category)
        await db_session.flush()

        offer = ServiceOffer(
            business_id=biz.id,
            category_id=category.id,
            name=f"Svc {uuid.uuid4().hex[:6]}",
            slug=f"svc-{uuid.uuid4().hex[:6]}",
            pricing_model="fixed",
            status="active",
        )
        db_session.add(offer)
        await db_session.flush()

        enquiry = Enquiry(
            reference=f"ENQ-{uuid.uuid4().hex[:8]}",
            customer_id=business_owner.id,
            business_id=biz.id,
            service_offer_id=offer.id,
            subject="test",
            message="test",
            status="draft",
        )
        db_session.add(enquiry)
        await db_session.flush()

        from app.domain.quote.models import Quote

        quote = Quote(
            reference=f"QUO-{uuid.uuid4().hex[:8]}",
            customer_id=business_owner.id,
            business_id=biz.id,
            enquiry_id=enquiry.id,
            service_offer_id=offer.id,
            amount="100.00",
            currency="GBP",
            status="draft",
        )
        db_session.add(quote)
        await db_session.flush()

        booking = Booking(
            reference=f"BKG-{uuid.uuid4().hex[:8]}",
            customer_id=business_owner.id,
            business_id=biz.id,
            quote_id=quote.id,
            enquiry_id=enquiry.id,
            service_offer_id=offer.id,
            requested_at=datetime.now(UTC),
            currency="GBP",
            status=BookingStatus.REQUESTED,
        )
        db_session.add(booking)
        await db_session.flush()

        service = ServiceExecutionService(db_session)
        with pytest.raises(ValidationError, match="confirmed or in_progress"):
            await service.create_from_booking(
                booking_id=booking.id,
                business_id=biz.id,
            )

    async def test_duplicate_execution_blocked(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Cannot create two executions for the same booking."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        with pytest.raises(ConflictError, match="already exists"):
            await service.create_from_booking(
                booking_id=confirmed_booking.id,
                business_id=biz.id,
            )

    async def test_valid_transitions(self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking):
        """Test valid state transitions."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        # Execution starts IN_PROGRESS (Start Work already clicked)
        assert execution.status == ServiceExecutionStatus.IN_PROGRESS
        assert execution.started_at is not None

        # IN_PROGRESS -> COMPLETED
        execution = await service.complete_service(execution, actor_id=business_owner.id)
        assert execution.status == ServiceExecutionStatus.COMPLETED
        assert execution.completed_at is not None
        assert execution.completed_by == business_owner.id

    async def test_invalid_transition_rejected(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Invalid state transitions are rejected."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        # Cannot go from IN_PROGRESS to SCHEDULED (invalid reverse transition)
        with pytest.raises(StateTransitionError):
            await service.transition(execution, ServiceExecutionStatus.SCHEDULED, actor_id=business_owner.id)

    async def test_cancel_from_in_progress(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Can cancel from IN_PROGRESS."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        execution = await service.cancel_service(execution, actor_id=business_owner.id)
        assert execution.status == ServiceExecutionStatus.CANCELLED

    async def test_no_show_from_scheduled(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Can mark no-show from SCHEDULED (legacy executions)."""
        from app.domain.service_execution.models import ServiceExecution

        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        # Create a scheduled execution directly (legacy path)
        execution = ServiceExecution(
            business_id=biz.id,
            customer_id=confirmed_booking.customer_id,
            booking_id=confirmed_booking.id,
            service_offer_id=confirmed_booking.service_offer_id,
            quote_id=confirmed_booking.quote_id,
            status=ServiceExecutionStatus.SCHEDULED,
            scheduled_at=confirmed_booking.requested_at,
        )
        execution = await service.execution_repo.create(execution)

        execution = await service.mark_no_show(execution, actor_id=business_owner.id)
        assert execution.status == ServiceExecutionStatus.NO_SHOW


class TestCompletionIdempotency:
    """Test that completion is idempotent."""

    async def test_repeated_completion_no_duplicates(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Repeated completion calls do not create duplicate records."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        # Execution starts IN_PROGRESS, complete directly
        execution = await service.complete_service(execution, actor_id=business_owner.id)

        assert execution.status == ServiceExecutionStatus.COMPLETED

        # Call complete again — should be idempotent
        execution = await service.complete_service(execution, actor_id=business_owner.id)
        assert execution.status == ServiceExecutionStatus.COMPLETED

        # Verify only one invoice exists
        from sqlalchemy import func, select

        result = await db_session.execute(
            select(func.count())
            .select_from(Invoice)
            .where(
                Invoice.service_execution_id == execution.id,
                Invoice.deleted_at.is_(None),
            )
        )
        invoice_count = result.scalar_one()
        assert invoice_count == 1

        # Verify only one primary ledger entry exists
        result = await db_session.execute(
            select(func.count())
            .select_from(ServiceLedgerEntry)
            .where(
                ServiceLedgerEntry.service_execution_id == execution.id,
                ServiceLedgerEntry.is_primary.is_(True),
                ServiceLedgerEntry.deleted_at.is_(None),
            )
        )
        ledger_count = result.scalar_one()
        assert ledger_count == 1


class TestCompletionIntegrity:
    """Test that completion creates invoice + ledger atomically."""

    async def test_completion_creates_invoice_and_ledger(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Completing a service creates an invoice and ledger entry."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        # Execution starts IN_PROGRESS, complete directly
        execution = await service.complete_service(execution, actor_id=business_owner.id)

        # Verify invoice was created
        from sqlalchemy import select

        result = await db_session.execute(
            select(Invoice).where(
                Invoice.service_execution_id == execution.id,
                Invoice.deleted_at.is_(None),
            )
        )
        invoice = result.scalar_one_or_none()
        assert invoice is not None
        assert str(invoice.total) == "150.00"
        assert invoice.currency == "GBP"
        assert invoice.payment_status == InvoicePaymentStatus.UNPAID
        assert invoice.status == InvoiceStatus.ISSUED

        # Verify line item
        result = await db_session.execute(
            select(InvoiceLineItem).where(
                InvoiceLineItem.invoice_id == invoice.id,
                InvoiceLineItem.deleted_at.is_(None),
            )
        )
        line_items = list(result.scalars().all())
        assert len(line_items) == 1
        assert str(line_items[0].line_total) == "150.00"

        # Verify ledger entry
        result = await db_session.execute(
            select(ServiceLedgerEntry).where(
                ServiceLedgerEntry.service_execution_id == execution.id,
                ServiceLedgerEntry.is_primary.is_(True),
                ServiceLedgerEntry.deleted_at.is_(None),
            )
        )
        ledger_entry = result.scalar_one_or_none()
        assert ledger_entry is not None
        assert str(ledger_entry.gross_amount) == "150.00"
        assert ledger_entry.currency == "GBP"
        assert ledger_entry.invoice_id == invoice.id
        assert ledger_entry.transaction_reference is not None


class TestTenantIsolation:
    """Test tenant isolation for Phase 13 domains."""

    async def test_cannot_access_other_business_execution(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """A business cannot access another business's service execution."""
        biz = business_owner._business
        service = ServiceExecutionService(db_session)

        execution = await service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )

        # Try to access with a different business ID
        other_biz_id = uuid.uuid4()
        with pytest.raises(AuthorizationError):
            await service.get_business_execution(execution.id, other_biz_id)

    async def test_cannot_create_execution_for_other_business_booking(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Cannot create execution for a booking that doesn't belong to your business."""
        other_biz_id = uuid.uuid4()
        service = ServiceExecutionService(db_session)

        with pytest.raises(AuthorizationError):
            await service.create_from_booking(
                booking_id=confirmed_booking.id,
                business_id=other_biz_id,
            )


class TestInvoiceService:
    """Test invoice service operations."""

    async def test_payment_status_update(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Payment status can be updated by authorized business user."""
        biz = business_owner._business
        exec_service = ServiceExecutionService(db_session)
        inv_service = InvoiceService(db_session)

        execution = await exec_service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )
        # Execution starts IN_PROGRESS, complete directly
        execution = await exec_service.complete_service(execution, actor_id=business_owner.id)

        # Get the invoice
        invoice = await inv_service.get_business_invoice(
            (
                await db_session.execute(
                    __import__("sqlalchemy").select(Invoice.id).where(Invoice.service_execution_id == execution.id)
                )
            ).scalar_one(),
            biz.id,
        )

        # Update payment status
        invoice = await inv_service.update_payment_status(
            invoice, InvoicePaymentStatus.PAID, actor_id=business_owner.id
        )
        assert invoice.payment_status == InvoicePaymentStatus.PAID

    async def test_void_invoice(self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking):
        """Voiding an invoice changes its status."""
        biz = business_owner._business
        exec_service = ServiceExecutionService(db_session)
        inv_service = InvoiceService(db_session)

        execution = await exec_service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )
        # Execution starts IN_PROGRESS, complete directly
        execution = await exec_service.complete_service(execution, actor_id=business_owner.id)

        from sqlalchemy import select

        result = await db_session.execute(select(Invoice.id).where(Invoice.service_execution_id == execution.id))
        invoice_id = result.scalar_one()

        invoice = await inv_service.get_invoice(invoice_id)
        invoice = await inv_service.update_payment_status(
            invoice, InvoicePaymentStatus.VOID, actor_id=business_owner.id
        )
        assert invoice.payment_status == InvoicePaymentStatus.VOID
        assert invoice.status == InvoiceStatus.VOID


class TestLedgerService:
    """Test ledger service operations."""

    async def test_ledger_summary(self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking):
        """Ledger summary returns correct totals."""
        biz = business_owner._business
        exec_service = ServiceExecutionService(db_session)
        ledger_service = LedgerService(db_session)

        execution = await exec_service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )
        # Execution starts IN_PROGRESS, complete directly
        execution = await exec_service.complete_service(execution, actor_id=business_owner.id)

        summary = await ledger_service.get_summary(biz.id)
        assert summary["total_entries"] == 1
        assert Decimal(summary["total_net"]) == Decimal("150.00")
        assert Decimal(summary["outstanding_amount"]) == Decimal("150.00")
        assert Decimal(summary["paid_amount"]) == Decimal("0.00")

    async def test_csv_export(self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking):
        """CSV export contains ledger data."""
        biz = business_owner._business
        exec_service = ServiceExecutionService(db_session)
        ledger_service = LedgerService(db_session)

        execution = await exec_service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )
        # Execution starts IN_PROGRESS, complete directly
        execution = await exec_service.complete_service(execution, actor_id=business_owner.id)

        csv_content = await ledger_service.export_csv(biz.id)
        assert "FIELDed" in csv_content
        assert "150.00" in csv_content
        assert "TOTALS" in csv_content

    async def test_pdf_export(self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking):
        """PDF export generates bytes."""
        biz = business_owner._business
        exec_service = ServiceExecutionService(db_session)
        ledger_service = LedgerService(db_session)

        execution = await exec_service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )
        # Execution starts IN_PROGRESS, complete directly
        execution = await exec_service.complete_service(execution, actor_id=business_owner.id)

        pdf_bytes = await ledger_service.export_pdf(biz.id)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"


class TestInvoicePDF:
    """Test invoice PDF generation."""

    async def test_generate_invoice_pdf(
        self, db_session: AsyncSession, business_owner: User, confirmed_booking: Booking
    ):
        """Invoice PDF is generated from persisted data."""
        biz = business_owner._business
        exec_service = ServiceExecutionService(db_session)
        inv_service = InvoiceService(db_session)

        execution = await exec_service.create_from_booking(
            booking_id=confirmed_booking.id,
            business_id=biz.id,
        )
        # Execution starts IN_PROGRESS, complete directly
        execution = await exec_service.complete_service(execution, actor_id=business_owner.id)

        from sqlalchemy import select

        result = await db_session.execute(select(Invoice.id).where(Invoice.service_execution_id == execution.id))
        invoice_id = result.scalar_one()

        invoice = await inv_service.get_invoice(invoice_id)
        pdf_bytes = await inv_service.generate_invoice_pdf(invoice)

        assert len(pdf_bytes) > 0
        # Check it's a valid PDF (starts with %PDF)
        assert pdf_bytes[:4] == b"%PDF"


class TestEnumTransitions:
    """Test state machine definitions."""

    async def test_service_execution_transitions_defined(self):
        """All service execution states have transition definitions."""
        for status in ServiceExecutionStatus:
            assert status in SERVICE_EXECUTION_TRANSITIONS

    async def test_terminal_states_have_no_transitions(self):
        """Terminal states have empty transition sets."""
        terminal = [
            ServiceExecutionStatus.COMPLETED,
            ServiceExecutionStatus.CANCELLED,
            ServiceExecutionStatus.NO_SHOW,
        ]
        for state in terminal:
            assert SERVICE_EXECUTION_TRANSITIONS[state] == set()
