"""Service Execution domain service.

Contains business logic for service execution lifecycle management.
The critical transaction is:

    ServiceExecution → COMPLETED
    → Invoice created
    → LedgerEntry created
    → Audit event recorded

These operations have transaction integrity — completion is idempotent
and repeated requests do not create duplicate records.

Only an appropriately authorized business user may mark a service
completed.  A customer must NOT be able to mark a service as completed.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.repository import BookingRepository
from app.domain.common.enums import (
    SERVICE_EXECUTION_TRANSITIONS,
    BookingStatus,
    InvoicePaymentStatus,
    InvoiceStatus,
    ServiceExecutionStatus,
)
from app.domain.invoice.models import Invoice, InvoiceLineItem
from app.domain.invoice.repository import InvoiceRepository
from app.domain.ledger.models import ServiceLedgerEntry
from app.domain.ledger.repository import LedgerRepository
from app.domain.outbox.models import OutboxEvent
from app.domain.quote.repository import QuoteRepository
from app.domain.service_execution.models import ServiceExecution
from app.domain.service_execution.repository import ServiceExecutionRepository
from app.domain.services.models import ServiceOffer
from app.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from app.logging import get_logger

logger = get_logger(__name__)


class ServiceExecutionService:
    """Service execution lifecycle management.

    Orchestrates the completion flow:
        COMPLETED → Invoice → LedgerEntry (atomically, idempotently)
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.execution_repo = ServiceExecutionRepository(session)
        self.invoice_repo = InvoiceRepository(session)
        self.ledger_repo = LedgerRepository(session)
        self.booking_repo = BookingRepository(session)
        self.quote_repo = QuoteRepository(session)

    # --- Creation ---

    async def create_from_booking(
        self,
        *,
        booking_id: uuid.UUID,
        business_id: uuid.UUID,
    ) -> ServiceExecution:
        """Create a service execution from a confirmed booking.

        The booking must be CONFIRMED or IN_PROGRESS and belong to the
        specified business.
        """
        # Check idempotency — execution already exists for this booking?
        existing = await self.execution_repo.get_by_booking_id(booking_id)
        if existing is not None:
            raise ConflictError(
                "Service execution already exists for this booking",
                details={"execution_id": str(existing.id), "status": existing.status},
            )

        booking = await self.booking_repo.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        if booking.business_id != business_id:
            raise AuthorizationError("Booking does not belong to this business")

        allowed_statuses = {BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS}
        if BookingStatus(booking.status) not in allowed_statuses:
            raise ValidationError(
                f"Booking must be confirmed or in_progress to create execution. "
                f"Current status: {booking.status}"
            )

        execution = ServiceExecution(
            business_id=business_id,
            customer_id=booking.customer_id,
            booking_id=booking.id,
            service_offer_id=booking.service_offer_id,
            quote_id=booking.quote_id,
            status=ServiceExecutionStatus.SCHEDULED,
            scheduled_at=booking.requested_at,
        )
        execution = await self.execution_repo.create(execution)

        logger.info(
            "service_execution_created",
            execution_id=str(execution.id),
            booking_id=str(booking_id),
            business_id=str(business_id),
        )

        return execution

    # --- Lifecycle ---

    async def transition(
        self,
        execution: ServiceExecution,
        target_status: ServiceExecutionStatus,
        *,
        actor_id: uuid.UUID | None = None,
        notes: str | None = None,
        completion_evidence: dict | None = None,
    ) -> ServiceExecution:
        """Transition a service execution to a new status.

        Validates the transition against the state machine.
        If transitioning to COMPLETED, atomically creates the invoice
        and ledger entry (idempotent).
        """
        current = ServiceExecutionStatus(execution.status)
        allowed = SERVICE_EXECUTION_TRANSITIONS.get(current, set())

        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition service execution from '{current.value}' to "
                f"'{target_status.value}'. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        old_status = execution.status

        # Update timestamps based on target status
        if target_status == ServiceExecutionStatus.IN_PROGRESS:
            execution.started_at = datetime.now(UTC)
        elif target_status == ServiceExecutionStatus.COMPLETED:
            execution.completed_at = datetime.now(UTC)
            execution.completed_by = actor_id
            if completion_evidence:
                execution.completion_evidence = completion_evidence

        if notes:
            execution.notes = notes

        execution.status = target_status
        execution = await self.execution_repo.update(execution)

        # If completed, create invoice + ledger entry atomically
        if target_status == ServiceExecutionStatus.COMPLETED:
            await self._create_completion_records(execution)
            # Cascade: booking → COMPLETED → enquiry → COMPLETED
            await self._cascade_booking_completion(execution)

        logger.info(
            "service_execution_transition",
            execution_id=str(execution.id),
            actor=str(actor_id) if actor_id else None,
            from_status=old_status,
            to_status=target_status.value,
        )

        # Emit outbox event for communication pipeline
        notification_title = f"Service {target_status.value}"
        notification_body = f"Service execution status: {target_status.value}"
        if target_status == ServiceExecutionStatus.COMPLETED:
            notification_title = "Service completed"
            notification_body = "Your service has been completed. You can now make payment."
        elif target_status == ServiceExecutionStatus.IN_PROGRESS:
            notification_title = "Service in progress"
            notification_body = "The business has started working on your service."

        await self._emit_outbox_event(
            business_id=execution.business_id,
            event_type=f"SERVICE_{target_status.value.upper()}",
            aggregate_id=execution.id,
            payload={
                "service_execution_id": str(execution.id),
                "booking_id": str(execution.booking_id),
                "customer_id": str(execution.customer_id),
                "status": target_status.value,
                "notification_title": notification_title,
                "notification_body": notification_body,
            },
        )

        return execution

    async def complete_service(
        self,
        execution: ServiceExecution,
        *,
        actor_id: uuid.UUID,
        notes: str | None = None,
        completion_evidence: dict | None = None,
    ) -> ServiceExecution:
        """Mark a service as completed.

        This is the primary completion entry point.  It is idempotent:
        if the execution is already COMPLETED, it returns the existing
        execution without creating duplicate records.
        """
        # Idempotency: if already completed, return as-is
        if ServiceExecutionStatus(execution.status) == ServiceExecutionStatus.COMPLETED:
            logger.info(
                "service_execution_already_completed",
                execution_id=str(execution.id),
            )
            return execution

        return await self.transition(
            execution,
            ServiceExecutionStatus.COMPLETED,
            actor_id=actor_id,
            notes=notes,
            completion_evidence=completion_evidence,
        )

    async def start_service(
        self,
        execution: ServiceExecution,
        *,
        actor_id: uuid.UUID,
    ) -> ServiceExecution:
        """Mark a service as in-progress."""
        return await self.transition(
            execution,
            ServiceExecutionStatus.IN_PROGRESS,
            actor_id=actor_id,
        )

    async def cancel_service(
        self,
        execution: ServiceExecution,
        *,
        actor_id: uuid.UUID,
        notes: str | None = None,
    ) -> ServiceExecution:
        """Cancel a service execution."""
        return await self.transition(
            execution,
            ServiceExecutionStatus.CANCELLED,
            actor_id=actor_id,
            notes=notes,
        )

    async def mark_no_show(
        self,
        execution: ServiceExecution,
        *,
        actor_id: uuid.UUID,
        notes: str | None = None,
    ) -> ServiceExecution:
        """Mark a customer as no-show."""
        return await self.transition(
            execution,
            ServiceExecutionStatus.NO_SHOW,
            actor_id=actor_id,
            notes=notes,
        )

    # --- Retrieval ---

    async def get_execution(self, execution_id: uuid.UUID) -> ServiceExecution:
        """Get a service execution by ID."""
        execution = await self.execution_repo.get_by_id(execution_id)
        if execution is None:
            raise NotFoundError("Service execution not found")
        return execution

    async def get_business_execution(
        self, execution_id: uuid.UUID, business_id: uuid.UUID
    ) -> ServiceExecution:
        """Get a service execution, verifying it belongs to the business."""
        execution = await self.get_execution(execution_id)
        if execution.business_id != business_id:
            raise AuthorizationError("Service execution does not belong to this business")
        return execution

    async def get_customer_execution(
        self, execution_id: uuid.UUID, customer_id: uuid.UUID
    ) -> ServiceExecution:
        """Get a service execution, verifying customer ownership."""
        execution = await self.get_execution(execution_id)
        if execution.customer_id != customer_id:
            raise AuthorizationError("Not your service execution")
        return execution

    async def list_business_executions(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceExecution]:
        """List service executions for a business."""
        return await self.execution_repo.get_by_business(
            business_id, status=status, limit=limit, offset=offset
        )

    async def list_customer_executions(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceExecution]:
        """List service executions for a customer."""
        return await self.execution_repo.get_by_customer(
            customer_id, status=status, limit=limit, offset=offset
        )

    # --- Internal: completion flow ---

    async def _create_completion_records(self, execution: ServiceExecution) -> None:
        """Atomically create invoice and ledger entry for a completed service.

        This method is idempotent — it checks for existing records before
        creating new ones.  This prevents duplicate invoices/ledger entries
        if completion is called multiple times.
        """
        # Idempotency check: does an invoice already exist?
        existing_invoice = await self.invoice_repo.get_by_service_execution_id(execution.id)
        if existing_invoice is not None:
            logger.info(
                "completion_records_already_exist",
                execution_id=str(execution.id),
                invoice_id=str(existing_invoice.id),
            )
            return

        # Resolve the quote for pricing data
        quote = None
        if execution.quote_id:
            quote = await self.quote_repo.get_by_id(execution.quote_id)

        # Resolve the service offer for description
        result = await self.session.execute(
            select(ServiceOffer).where(
                ServiceOffer.id == execution.service_offer_id,
                ServiceOffer.deleted_at.is_(None),
            )
        )
        service_offer = result.scalar_one_or_none()
        service_name = service_offer.name if service_offer else "Service"

        # Determine currency from booking
        booking = await self.booking_repo.get_by_id(execution.booking_id)
        currency = booking.currency if booking else "GBP"

        # Calculate amounts from quote (deterministic, no LLM)
        amount = Decimal(str(quote.amount)) if quote else Decimal("0.00")

        discount = Decimal("0.00")
        tax = Decimal("0.00")
        total = amount - discount + tax

        # Generate invoice number
        invoice_number = await self.invoice_repo.get_next_invoice_number(execution.business_id)

        now = datetime.now(UTC)

        # Create invoice
        invoice = Invoice(
            business_id=execution.business_id,
            customer_id=execution.customer_id,
            service_execution_id=execution.id,
            booking_id=execution.booking_id,
            quote_id=execution.quote_id,
            invoice_number=invoice_number,
            issue_date=now,
            currency=currency,
            subtotal=str(amount),
            discount=str(discount),
            tax=str(tax),
            total=str(total),
            payment_status=InvoicePaymentStatus.UNPAID,
            status=InvoiceStatus.ISSUED,
        )
        invoice = await self.invoice_repo.create(invoice)

        # Create invoice line item
        line_item = InvoiceLineItem(
            invoice_id=invoice.id,
            description=service_name,
            service_reference=service_offer.slug if service_offer else None,
            quantity="1.00",
            unit_price=str(amount),
            discount=str(discount),
            tax=str(tax),
            line_total=str(total),
            currency=currency,
            sort_order=0,
        )
        self.session.add(line_item)
        await self.session.flush()

        # Generate transaction reference
        tx_ref = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        # Create primary ledger entry
        net_amount = total - discount
        ledger_entry = ServiceLedgerEntry(
            business_id=execution.business_id,
            customer_id=execution.customer_id,
            service_execution_id=execution.id,
            booking_id=execution.booking_id,
            quote_id=execution.quote_id,
            invoice_id=invoice.id,
            service_offer_id=execution.service_offer_id,
            completion_date=now,
            gross_amount=str(amount),
            discount=str(discount),
            tax=str(tax),
            net_amount=str(net_amount),
            currency=currency,
            payment_status=InvoicePaymentStatus.UNPAID,
            is_primary=True,
            transaction_reference=tx_ref,
        )
        ledger_entry = await self.ledger_repo.create(ledger_entry)

        logger.info(
            "completion_records_created",
            execution_id=str(execution.id),
            invoice_id=str(invoice.id),
            invoice_number=invoice_number,
            ledger_entry_id=str(ledger_entry.id),
            transaction_reference=tx_ref,
            total=str(total),
            currency=currency,
        )

        # Emit INVOICE_ISSUED outbox event
        await self._emit_outbox_event(
            business_id=execution.business_id,
            event_type="INVOICE_ISSUED",
            aggregate_id=invoice.id,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice_number,
                "customer_id": str(execution.customer_id),
                "service_execution_id": str(execution.id),
                "total": str(total),
                "currency": currency,
                "notification_title": f"Invoice {invoice_number} issued",
                "notification_body": f"Invoice {invoice_number} for {currency} {total} is ready for payment.",
            },
        )

    async def _cascade_booking_completion(self, execution: ServiceExecution) -> None:
        """Cascade execution completion to booking and enquiry.

        If the linked booking is CONFIRMED or IN_PROGRESS, transition
        it to COMPLETED.  This in turn cascades to the enquiry
        (handled inside BookingService.transition_booking).

        Idempotent: if booking is already COMPLETED, skip.
        """
        booking = await self.booking_repo.get_by_id(execution.booking_id)
        if booking is None:
            return

        current_status = BookingStatus(booking.status)
        if current_status == BookingStatus.COMPLETED:
            return  # Already completed — idempotent

        if current_status not in (BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS):
            return  # Cannot cascade from this state

        # Transition booking to COMPLETED
        from app.domain.booking.service import BookingService

        booking_service = BookingService(self.session)
        with contextlib.suppress(StateTransitionError):
            await booking_service.transition_booking(
                booking, BookingStatus.COMPLETED, actor="system"
            )
        # Suppressed: StateTransitionError means another path already completed it

    async def _emit_outbox_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Create an outbox event in the same transaction."""
        event = OutboxEvent(
            business_id=business_id,
            event_type=event_type,
            aggregate_type="service_execution",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:service_execution:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(UTC),
        )
        self.session.add(event)
        await self.session.flush()
