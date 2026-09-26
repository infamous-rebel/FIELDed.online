"""Booking automation service.

Orchestrates downstream operations triggered by booking lifecycle
events, using the outbox pattern for reliability.

Architecture:
    Booking transition (CONFIRMED / CANCELLED / COMPLETED / etc.)
    → Outbox event (BOOKING_*)
    → Outbox worker picks up event
    → BookingAutomationService processes event
    → Each downstream operation tracked independently
    → Failures recorded, retried independently
    → Booking/payment state never corrupted

Downstream operations:
    - Calendar synchronization (create/update/cancel)
    - Service execution auto-creation (on CONFIRMED)
    - Payment preparation tracking (on COMPLETED)

Key invariants:
    - Each operation is independently retryable and idempotent.
    - A failure in email, SMS, WhatsApp, or calendar does NOT
      corrupt the authoritative booking or payment state.
    - Each operation's status is recorded separately.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.booking.repository import BookingRepository
from app.domain.booking_automation.models import BookingAutomationStatus
from app.domain.booking_automation.repository import BookingAutomationStatusRepository
from app.domain.common.enums import BookingStatus
from app.domain.service_execution.service import ServiceExecutionService
from app.logging import get_logger

logger = get_logger(__name__)

# Operation type constants
OP_CALENDAR_SYNC = "CALENDAR_SYNC"
OP_SERVICE_EXECUTION = "SERVICE_EXECUTION"
OP_PAYMENT_PREP = "PAYMENT_PREP"

# Max retry attempts before marking EXHAUSTED
MAX_ATTEMPTS = 5

# Booking event types that trigger automation
BOOKING_AUTOMATION_EVENTS = frozenset(
    {
        "BOOKING_CONFIRMED",
        "BOOKING_CANCELLED",
        "BOOKING_COMPLETED",
        "BOOKING_IN_PROGRESS",
    }
)


class BookingAutomationService:
    """Orchestrates downstream booking automation operations.

    Called by the outbox worker for each BOOKING_* event.
    Each downstream operation is tracked independently in the
    booking_automation_status table.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        app_secret: str = "",
        calendar_sync_enabled: bool = True,
    ) -> None:
        self.session = session
        self._app_secret = app_secret
        self._calendar_sync_enabled = calendar_sync_enabled
        self._status_repo = BookingAutomationStatusRepository(session)
        self._booking_repo = BookingRepository(session)

    async def process_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> None:
        """Process a BOOKING_* outbox event.

        Dispatches to the appropriate handler based on event type.
        Each downstream operation is wrapped in its own try/except
        so failures are isolated.
        """
        if event_type not in BOOKING_AUTOMATION_EVENTS:
            return

        booking_id_str = payload.get("booking_id")
        if not booking_id_str:
            return

        booking_id = uuid.UUID(booking_id_str) if isinstance(booking_id_str, str) else booking_id_str

        try:
            if event_type == "BOOKING_CONFIRMED":
                await self._handle_confirmed(business_id, booking_id, event_type)
            elif event_type == "BOOKING_CANCELLED":
                await self._handle_cancelled(business_id, booking_id, event_type)
            elif event_type == "BOOKING_COMPLETED":
                await self._handle_completed(business_id, booking_id, event_type)
            elif event_type == "BOOKING_IN_PROGRESS":
                await self._handle_in_progress(business_id, booking_id, event_type)
        except Exception:
            logger.exception(
                "booking_automation_event_failed",
                event_type=event_type,
                booking_id=str(booking_id),
                business_id=str(business_id),
            )

    async def retry_failed_operations(self) -> int:
        """Retry failed automation operations.

        Called periodically by the outbox worker.
        Returns the number of operations successfully retried.
        """
        retryable = await self._status_repo.get_retryable(batch_size=20)
        if not retryable:
            return 0

        retried = 0
        for record in retryable:
            try:
                booking = await self._booking_repo.get_by_id(record.booking_id)
                if booking is None:
                    await self._status_repo.mark_exhausted(record, error="Booking not found")
                    continue

                success = await self._retry_operation(record, booking)
                if success:
                    retried += 1
                await self.session.commit()
            except Exception:
                logger.exception(
                    "booking_automation_retry_failed",
                    record_id=str(record.id),
                    operation=record.operation_type,
                    booking_id=str(record.booking_id),
                )
                try:
                    await self.session.rollback()
                except Exception:
                    pass

        return retried

    # --- Event handlers ---

    async def _handle_confirmed(
        self,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
        event_type: str,
    ) -> None:
        """Handle BOOKING_CONFIRMED: calendar sync + service execution."""
        # 1. Calendar sync (create event)
        if self._calendar_sync_enabled:
            await self._run_operation(
                business_id=business_id,
                booking_id=booking_id,
                operation_type=OP_CALENDAR_SYNC,
                event_type=event_type,
                operation_fn=self._do_calendar_sync,
            )

        # 2. Auto-create service execution
        await self._run_operation(
            business_id=business_id,
            booking_id=booking_id,
            operation_type=OP_SERVICE_EXECUTION,
            event_type=event_type,
            operation_fn=self._do_create_service_execution,
        )

    async def _handle_cancelled(
        self,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
        event_type: str,
    ) -> None:
        """Handle BOOKING_CANCELLED: calendar cancel + mark service execution N/A."""
        # 1. Calendar sync (cancel event)
        if self._calendar_sync_enabled:
            await self._run_operation(
                business_id=business_id,
                booking_id=booking_id,
                operation_type=OP_CALENDAR_SYNC,
                event_type=event_type,
                operation_fn=self._do_calendar_cancel,
            )

        # 2. Service execution — not applicable (booking cancelled before execution)
        await self._run_operation(
            business_id=business_id,
            booking_id=booking_id,
            operation_type=OP_SERVICE_EXECUTION,
            event_type=event_type,
            operation_fn=self._do_service_execution_not_applicable,
        )

    async def _handle_completed(
        self,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
        event_type: str,
    ) -> None:
        """Handle BOOKING_COMPLETED: payment prep tracking."""
        # Service execution already created invoice during its own completion flow.
        # Track payment prep readiness.
        await self._run_operation(
            business_id=business_id,
            booking_id=booking_id,
            operation_type=OP_PAYMENT_PREP,
            event_type=event_type,
            operation_fn=self._do_payment_prep,
        )

    async def _handle_in_progress(
        self,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
        event_type: str,
    ) -> None:
        """Handle BOOKING_IN_PROGRESS: ensure service execution exists."""
        # If service execution wasn't created on CONFIRMED (e.g., it was
        # created manually), just track it as already done.
        await self._run_operation(
            business_id=business_id,
            booking_id=booking_id,
            operation_type=OP_SERVICE_EXECUTION,
            event_type=event_type,
            operation_fn=self._do_service_execution_already_done,
        )

    # --- Operation runner ---

    async def _run_operation(
        self,
        *,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
        operation_type: str,
        event_type: str,
        operation_fn: callable,
    ) -> None:
        """Run a single downstream operation with status tracking.

        Creates or retrieves the status record, checks if already
        succeeded (idempotency), executes the operation, and records
        the result.
        """
        status = await self._get_or_create_status(
            business_id=business_id,
            booking_id=booking_id,
            operation_type=operation_type,
            event_type=event_type,
        )

        # Idempotency: already succeeded or not applicable
        if status.status in ("SUCCESS", "NOT_APPLICABLE"):
            return

        try:
            evidence = await operation_fn(status)
            await self._status_repo.mark_success(status, evidence=evidence)
            await self.session.commit()

            logger.info(
                "booking_automation_operation_succeeded",
                booking_id=str(booking_id),
                operation=operation_type,
                business_id=str(business_id),
            )
        except Exception as exc:
            error_msg = str(exc)[:1000]
            status.attempt_count = (status.attempt_count or 0) + 1

            if status.attempt_count >= MAX_ATTEMPTS:
                await self._status_repo.mark_exhausted(status, error=error_msg)
                logger.error(
                    "booking_automation_operation_exhausted",
                    booking_id=str(booking_id),
                    operation=operation_type,
                    attempts=status.attempt_count,
                    error=error_msg,
                )
            else:
                await self._status_repo.mark_failed(status, error=error_msg)
                logger.warning(
                    "booking_automation_operation_failed",
                    booking_id=str(booking_id),
                    operation=operation_type,
                    attempt=status.attempt_count,
                    error=error_msg,
                )

            try:
                await self.session.commit()
            except Exception:
                logger.exception("failed_to_commit_automation_status")
                await self.session.rollback()

    async def _retry_operation(
        self,
        record: BookingAutomationStatus,
        booking: Booking,
    ) -> bool:
        """Retry a single failed operation. Returns True if succeeded."""
        operation_map = {
            OP_CALENDAR_SYNC: self._do_calendar_sync_for_booking,
            OP_SERVICE_EXECUTION: self._do_create_service_execution_for_booking,
            OP_PAYMENT_PREP: self._do_payment_prep_for_booking,
        }

        fn = operation_map.get(record.operation_type)
        if fn is None:
            await self._status_repo.mark_exhausted(record, error=f"Unknown operation: {record.operation_type}")
            return False

        try:
            evidence = await fn(record, booking)
            await self._status_repo.mark_success(record, evidence=evidence)
            return True
        except Exception as exc:
            error_msg = str(exc)[:1000]
            record.attempt_count = (record.attempt_count or 0) + 1

            if record.attempt_count >= MAX_ATTEMPTS:
                await self._status_repo.mark_exhausted(record, error=error_msg)
            else:
                await self._status_repo.mark_failed(record, error=error_msg)
            return False

    # --- Downstream operations ---

    async def _do_calendar_sync(self, status: BookingAutomationStatus) -> dict | None:
        """Calendar sync: create event for the booking."""
        booking = await self._booking_repo.get_by_id(status.booking_id)
        if booking is None:
            raise ValueError("Booking not found for calendar sync")

        return await self._do_calendar_sync_for_booking(status, booking)

    async def _do_calendar_sync_for_booking(
        self,
        status: BookingAutomationStatus,
        booking: Booking,
    ) -> dict | None:
        """Calendar sync implementation (used by both initial + retry)."""
        from app.domain.calendar.sync_service import CalendarSyncService

        sync_service = CalendarSyncService(self.session, app_secret=self._app_secret)

        current_status = BookingStatus(booking.status)
        if current_status == BookingStatus.CANCELLED:
            result = await sync_service.sync_booking_cancelled(booking)
        else:
            result = await sync_service.sync_booking_confirmed(booking)

        if result is None:
            return {"result": "no_active_connection"}

        if result.status == "SYNCED":
            return {
                "result": "synced",
                "calendar_event_id": result.calendar_event_id,
                "provider": result.provider,
            }
        elif result.status == "FAILED":
            raise RuntimeError(result.last_error or "Calendar sync failed")

        return {"result": result.status}

    async def _do_calendar_cancel(self, status: BookingAutomationStatus) -> dict | None:
        """Calendar cancel: delete event for the booking."""
        booking = await self._booking_repo.get_by_id(status.booking_id)
        if booking is None:
            raise ValueError("Booking not found for calendar cancel")

        from app.domain.calendar.sync_service import CalendarSyncService

        sync_service = CalendarSyncService(self.session, app_secret=self._app_secret)
        result = await sync_service.sync_booking_cancelled(booking)

        if result is None:
            return {"result": "nothing_to_cancel"}

        if result.status == "CANCELLED":
            return {"result": "cancelled", "calendar_event_id": result.calendar_event_id}

        if result.last_error:
            raise RuntimeError(result.last_error)

        return {"result": result.status}

    async def _do_create_service_execution(self, status: BookingAutomationStatus) -> dict | None:
        """Auto-create service execution from confirmed booking."""
        booking = await self._booking_repo.get_by_id(status.booking_id)
        if booking is None:
            raise ValueError("Booking not found for service execution")

        return await self._do_create_service_execution_for_booking(status, booking)

    async def _do_create_service_execution_for_booking(
        self,
        status: BookingAutomationStatus,
        booking: Booking,
    ) -> dict | None:
        """Service execution creation (used by both initial + retry)."""
        service = ServiceExecutionService(self.session)
        execution = await service.create_from_booking(
            booking_id=booking.id,
            business_id=booking.business_id,
        )
        return {
            "result": "created",
            "service_execution_id": str(execution.id),
        }

    async def _do_service_execution_not_applicable(self, status: BookingAutomationStatus) -> dict | None:
        """Mark service execution as not applicable (booking cancelled)."""
        # Check if execution was already created before cancellation
        from app.domain.service_execution.repository import ServiceExecutionRepository

        exec_repo = ServiceExecutionRepository(self.session)
        existing = await exec_repo.get_by_booking_id(status.booking_id)
        if existing:
            return {"result": "already_exists", "service_execution_id": str(existing.id)}
        return None  # Will be marked NOT_APPLICABLE by caller

    async def _do_service_execution_already_done(self, status: BookingAutomationStatus) -> dict | None:
        """Service execution already in progress — mark as done."""
        from app.domain.service_execution.repository import ServiceExecutionRepository

        exec_repo = ServiceExecutionRepository(self.session)
        existing = await exec_repo.get_by_booking_id(status.booking_id)
        if existing:
            return {"result": "already_exists", "service_execution_id": str(existing.id)}
        # If no execution exists yet, try creating it
        return await self._do_create_service_execution(status)

    async def _do_payment_prep(self, status: BookingAutomationStatus) -> dict | None:
        """Check payment readiness for completed booking."""
        booking = await self._booking_repo.get_by_id(status.booking_id)
        if booking is None:
            raise ValueError("Booking not found for payment prep")

        return await self._do_payment_prep_for_booking(status, booking)

    async def _do_payment_prep_for_booking(
        self,
        status: BookingAutomationStatus,
        booking: Booking,
    ) -> dict | None:
        """Payment prep check (used by both initial + retry)."""
        from app.domain.invoice.repository import InvoiceRepository
        from app.domain.service_execution.repository import ServiceExecutionRepository

        exec_repo = ServiceExecutionRepository(self.session)
        execution = await exec_repo.get_by_booking_id(booking.id)

        if execution is None:
            return {"result": "no_execution_yet"}

        invoice_repo = InvoiceRepository(self.session)
        invoice = await invoice_repo.get_by_service_execution_id(execution.id)

        if invoice is None:
            return {"result": "no_invoice_yet"}

        return {
            "result": "ready",
            "invoice_id": str(invoice.id),
            "invoice_total": str(invoice.total),
            "invoice_currency": invoice.currency,
        }

    # --- Helpers ---

    async def _get_or_create_status(
        self,
        *,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
        operation_type: str,
        event_type: str,
    ) -> BookingAutomationStatus:
        """Get or create an automation status record."""
        existing = await self._status_repo.get_by_booking_and_operation(
            booking_id=booking_id,
            operation_type=operation_type,
        )
        if existing:
            return existing

        record = BookingAutomationStatus(
            business_id=business_id,
            booking_id=booking_id,
            operation_type=operation_type,
            triggering_event=event_type,
            status="PENDING",
        )
        return await self._status_repo.create(record)

    async def get_automation_status(
        self,
        business_id: uuid.UUID,
        booking_id: uuid.UUID,
    ) -> list[dict]:
        """Get automation status for a booking (for API exposure)."""
        records = await self._status_repo.get_by_booking(booking_id)
        return [
            {
                "operation_type": r.operation_type,
                "status": r.status,
                "attempt_count": r.attempt_count,
                "last_error": r.last_error,
                "last_attempted_at": r.last_attempted_at.isoformat() if r.last_attempted_at else None,
                "result_evidence": r.result_evidence,
            }
            for r in records
        ]
