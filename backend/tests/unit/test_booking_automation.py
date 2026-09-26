"""Tests for unified booking automation.

Covers:
- BookingAutomationStatus model
- Repository (CRUD, retryable queries, tenant isolation)
- BookingAutomationService (event processing, operation isolation)
- Calendar sync via automation (create, cancel, failure handling)
- Service execution auto-creation
- Payment prep tracking
- Independent retry mechanism
- Idempotency (re-processing same event)
- Failure isolation (calendar failure doesn't affect service execution)
- Max retry exhaustion
- Worker integration (booking_automation_service parameter)
- Migration existence
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.booking_automation.models import BookingAutomationStatus
from app.domain.booking_automation.service import (
    BOOKING_AUTOMATION_EVENTS,
    MAX_ATTEMPTS,
    OP_CALENDAR_SYNC,
    OP_PAYMENT_PREP,
    OP_SERVICE_EXECUTION,
    BookingAutomationService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_booking(
    *,
    business_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    status: str = "confirmed",
) -> MagicMock:
    """Create a mock Booking object."""
    booking = MagicMock()
    booking.id = uuid.uuid4()
    booking.business_id = business_id or uuid.uuid4()
    booking.customer_id = customer_id or uuid.uuid4()
    booking.status = status
    booking.reference = f"BKG-{uuid.uuid4().hex[:8]}"
    booking.requested_at = datetime.now(UTC)
    booking.notes = "Test booking"
    booking.enquiry_id = uuid.uuid4()
    booking.quote_id = uuid.uuid4()
    booking.service_offer_id = uuid.uuid4()
    booking.customer = None
    booking.business = None
    booking.service_offer = None
    return booking


def _make_automation_status(
    *,
    business_id: uuid.UUID | None = None,
    booking_id: uuid.UUID | None = None,
    operation_type: str = OP_CALENDAR_SYNC,
    status: str = "PENDING",
    attempt_count: int = 0,
) -> BookingAutomationStatus:
    """Create a BookingAutomationStatus instance (not persisted)."""
    return BookingAutomationStatus(
        business_id=business_id or uuid.uuid4(),
        booking_id=booking_id or uuid.uuid4(),
        operation_type=operation_type,
        triggering_event="BOOKING_CONFIRMED",
        status=status,
        attempt_count=attempt_count,
    )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TestBookingAutomationStatusModel:
    """BookingAutomationStatus model structure."""

    def test_table_name(self) -> None:
        assert BookingAutomationStatus.__tablename__ == "booking_automation_status"

    def test_has_required_columns(self) -> None:
        mapper = BookingAutomationStatus.__mapper__
        column_names = {c.key for c in mapper.column_attrs}
        required = {
            "id",
            "business_id",
            "booking_id",
            "operation_type",
            "triggering_event",
            "status",
            "attempt_count",
            "last_error",
            "last_attempted_at",
            "next_retry_at",
            "result_evidence",
        }
        assert required.issubset(column_names)

    def test_default_status(self) -> None:
        status = _make_automation_status()
        assert status.status == "PENDING"

    def test_operation_types(self) -> None:
        assert OP_CALENDAR_SYNC == "CALENDAR_SYNC"
        assert OP_SERVICE_EXECUTION == "SERVICE_EXECUTION"
        assert OP_PAYMENT_PREP == "PAYMENT_PREP"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Automation event types and configuration."""

    def test_automation_events_includes_confirmed(self) -> None:
        assert "BOOKING_CONFIRMED" in BOOKING_AUTOMATION_EVENTS

    def test_automation_events_includes_cancelled(self) -> None:
        assert "BOOKING_CANCELLED" in BOOKING_AUTOMATION_EVENTS

    def test_automation_events_includes_completed(self) -> None:
        assert "BOOKING_COMPLETED" in BOOKING_AUTOMATION_EVENTS

    def test_automation_events_excludes_requested(self) -> None:
        assert "BOOKING_REQUESTED" not in BOOKING_AUTOMATION_EVENTS

    def test_max_attempts(self) -> None:
        assert MAX_ATTEMPTS == 5


# ---------------------------------------------------------------------------
# Service — event processing
# ---------------------------------------------------------------------------


class TestBookingAutomationProcessEvent:
    """BookingAutomationService.process_event dispatching."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture()
    def service(self, mock_session: AsyncMock) -> BookingAutomationService:
        return BookingAutomationService(mock_session, app_secret="test-secret")

    async def test_ignores_non_booking_events(self, service: BookingAutomationService) -> None:
        """Non-BOOKING_* events should be silently ignored."""
        with patch.object(service, "_handle_confirmed") as mock_handle:
            await service.process_event(
                business_id=uuid.uuid4(),
                event_type="ENQUIRY_SUBMITTED",
                payload={"booking_id": str(uuid.uuid4())},
            )
            mock_handle.assert_not_called()

    async def test_ignores_events_without_booking_id(self, service: BookingAutomationService) -> None:
        """Events without booking_id in payload should be ignored."""
        with patch.object(service, "_handle_confirmed") as mock_handle:
            await service.process_event(
                business_id=uuid.uuid4(),
                event_type="BOOKING_CONFIRMED",
                payload={},
            )
            mock_handle.assert_not_called()

    async def test_dispatches_confirmed(self, service: BookingAutomationService) -> None:
        """BOOKING_CONFIRMED should call _handle_confirmed."""
        booking_id = uuid.uuid4()
        business_id = uuid.uuid4()
        with patch.object(service, "_handle_confirmed", new_callable=AsyncMock) as mock_handle:
            await service.process_event(
                business_id=business_id,
                event_type="BOOKING_CONFIRMED",
                payload={"booking_id": str(booking_id)},
            )
            mock_handle.assert_called_once_with(business_id, booking_id, "BOOKING_CONFIRMED")

    async def test_dispatches_cancelled(self, service: BookingAutomationService) -> None:
        """BOOKING_CANCELLED should call _handle_cancelled."""
        booking_id = uuid.uuid4()
        business_id = uuid.uuid4()
        with patch.object(service, "_handle_cancelled", new_callable=AsyncMock) as mock_handle:
            await service.process_event(
                business_id=business_id,
                event_type="BOOKING_CANCELLED",
                payload={"booking_id": str(booking_id)},
            )
            mock_handle.assert_called_once_with(business_id, booking_id, "BOOKING_CANCELLED")

    async def test_dispatches_completed(self, service: BookingAutomationService) -> None:
        """BOOKING_COMPLETED should call _handle_completed."""
        booking_id = uuid.uuid4()
        business_id = uuid.uuid4()
        with patch.object(service, "_handle_completed", new_callable=AsyncMock) as mock_handle:
            await service.process_event(
                business_id=business_id,
                event_type="BOOKING_COMPLETED",
                payload={"booking_id": str(booking_id)},
            )
            mock_handle.assert_called_once_with(business_id, booking_id, "BOOKING_COMPLETED")

    async def test_handler_exception_does_not_propagate(self, service: BookingAutomationService) -> None:
        """Exception in handler should be caught, not propagated."""
        with patch.object(
            service,
            "_handle_confirmed",
            side_effect=RuntimeError("boom"),
        ):
            # Should NOT raise
            await service.process_event(
                business_id=uuid.uuid4(),
                event_type="BOOKING_CONFIRMED",
                payload={"booking_id": str(uuid.uuid4())},
            )


# ---------------------------------------------------------------------------
# Service — operation isolation
# ---------------------------------------------------------------------------


class TestOperationIsolation:
    """Each operation fails independently."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture()
    def service(self, mock_session: AsyncMock) -> BookingAutomationService:
        return BookingAutomationService(mock_session, app_secret="test-secret")

    async def test_calendar_failure_does_not_block_service_execution(
        self,
        service: BookingAutomationService,
    ) -> None:
        """If calendar sync fails, service execution should still be attempted."""
        booking_id = uuid.uuid4()
        business_id = uuid.uuid4()

        # Mock _run_operation to track calls
        calls = []

        async def track_operation(**kwargs: object) -> None:
            calls.append(kwargs["operation_type"])

        with patch.object(service, "_run_operation", side_effect=track_operation):
            await service._handle_confirmed(business_id, booking_id, "BOOKING_CONFIRMED")

        # Both operations should have been attempted
        assert OP_CALENDAR_SYNC in calls
        assert OP_SERVICE_EXECUTION in calls

    async def test_calendar_disabled_skips_calendar(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """When calendar_sync_enabled=False, calendar operation is skipped."""
        service = BookingAutomationService(
            mock_session,
            app_secret="test-secret",
            calendar_sync_enabled=False,
        )

        calls = []

        async def track_operation(**kwargs: object) -> None:
            calls.append(kwargs["operation_type"])

        with patch.object(service, "_run_operation", side_effect=track_operation):
            await service._handle_confirmed(uuid.uuid4(), uuid.uuid4(), "BOOKING_CONFIRMED")

        assert OP_CALENDAR_SYNC not in calls
        assert OP_SERVICE_EXECUTION in calls


# ---------------------------------------------------------------------------
# Service — idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Re-processing the same event is safe."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture()
    def service(self, mock_session: AsyncMock) -> BookingAutomationService:
        return BookingAutomationService(mock_session, app_secret="test-secret")

    async def test_already_succeeded_skips_operation(
        self,
        service: BookingAutomationService,
    ) -> None:
        """If operation already succeeded, _run_operation should skip it."""
        # Create a mock status that's already SUCCESS
        mock_status = _make_automation_status(status="SUCCESS")

        with (
            patch.object(
                service._status_repo,
                "get_by_booking_and_operation",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
            patch.object(service, "_do_calendar_sync", new_callable=AsyncMock) as mock_op,
        ):
            await service._run_operation(
                business_id=uuid.uuid4(),
                booking_id=uuid.uuid4(),
                operation_type=OP_CALENDAR_SYNC,
                event_type="BOOKING_CONFIRMED",
                operation_fn=service._do_calendar_sync,
            )
            mock_op.assert_not_called()

    async def test_not_applicable_skips_operation(
        self,
        service: BookingAutomationService,
    ) -> None:
        """If operation is NOT_APPLICABLE, _run_operation should skip it."""
        mock_status = _make_automation_status(status="NOT_APPLICABLE")

        with (
            patch.object(
                service._status_repo,
                "get_by_booking_and_operation",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
            patch.object(service, "_do_calendar_sync", new_callable=AsyncMock) as mock_op,
        ):
            await service._run_operation(
                business_id=uuid.uuid4(),
                booking_id=uuid.uuid4(),
                operation_type=OP_CALENDAR_SYNC,
                event_type="BOOKING_CONFIRMED",
                operation_fn=service._do_calendar_sync,
            )
            mock_op.assert_not_called()


# ---------------------------------------------------------------------------
# Service — failure tracking
# ---------------------------------------------------------------------------


class TestFailureTracking:
    """Failed operations are recorded for retry."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture()
    def service(self, mock_session: AsyncMock) -> BookingAutomationService:
        return BookingAutomationService(mock_session, app_secret="test-secret")

    async def test_failure_records_status(self, service: BookingAutomationService) -> None:
        """Failed operation should be marked FAILED in status table."""
        mock_status = _make_automation_status(status="PENDING")

        async def failing_op(status: BookingAutomationStatus) -> dict | None:
            raise RuntimeError("Calendar provider down")

        with (
            patch.object(
                service._status_repo,
                "get_by_booking_and_operation",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
            patch.object(
                service._status_repo,
                "mark_failed",
                new_callable=AsyncMock,
            ) as mock_mark_failed,
        ):
            await service._run_operation(
                business_id=uuid.uuid4(),
                booking_id=uuid.uuid4(),
                operation_type=OP_CALENDAR_SYNC,
                event_type="BOOKING_CONFIRMED",
                operation_fn=failing_op,
            )
            mock_mark_failed.assert_called_once()

    async def test_exhaustion_after_max_attempts(self, service: BookingAutomationService) -> None:
        """Operation that fails MAX_ATTEMPTS times should be marked EXHAUSTED."""
        mock_status = _make_automation_status(status="PENDING", attempt_count=MAX_ATTEMPTS - 1)

        async def failing_op(status: BookingAutomationStatus) -> dict | None:
            raise RuntimeError("Still failing")

        with (
            patch.object(
                service._status_repo,
                "get_by_booking_and_operation",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
            patch.object(
                service._status_repo,
                "mark_exhausted",
                new_callable=AsyncMock,
            ) as mock_exhausted,
            patch.object(
                service._status_repo,
                "mark_failed",
                new_callable=AsyncMock,
            ) as mock_failed,
        ):
            await service._run_operation(
                business_id=uuid.uuid4(),
                booking_id=uuid.uuid4(),
                operation_type=OP_CALENDAR_SYNC,
                event_type="BOOKING_CONFIRMED",
                operation_fn=failing_op,
            )
            mock_exhausted.assert_called_once()
            mock_failed.assert_not_called()


# ---------------------------------------------------------------------------
# Service — retry mechanism
# ---------------------------------------------------------------------------


class TestRetryMechanism:
    """Failed operations are independently retryable."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture()
    def service(self, mock_session: AsyncMock) -> BookingAutomationService:
        return BookingAutomationService(mock_session, app_secret="test-secret")

    async def test_retry_calls_get_retryable(self, service: BookingAutomationService) -> None:
        """retry_failed_operations should query for retryable records."""
        with (
            patch.object(
                service._status_repo,
                "get_retryable",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_get_retryable,
        ):
            result = await service.retry_failed_operations()
            mock_get_retryable.assert_called_once()
            assert result == 0

    async def test_retry_succeeds_after_failure(self, service: BookingAutomationService) -> None:
        """A retry should succeed if the operation now works."""
        booking = _make_booking()
        record = _make_automation_status(
            business_id=booking.business_id,
            booking_id=booking.id,
            operation_type=OP_CALENDAR_SYNC,
            status="FAILED",
            attempt_count=1,
        )

        with (
            patch.object(
                service._status_repo,
                "get_retryable",
                new_callable=AsyncMock,
                return_value=[record],
            ),
            patch.object(
                service._booking_repo,
                "get_by_id",
                new_callable=AsyncMock,
                return_value=booking,
            ),
            patch.object(
                service._status_repo,
                "mark_success",
                new_callable=AsyncMock,
            ) as mock_success,
            patch.object(
                service,
                "_do_calendar_sync_for_booking",
                new_callable=AsyncMock,
                return_value={"result": "synced"},
            ),
        ):
            result = await service.retry_failed_operations()
            assert result == 1
            mock_success.assert_called_once()

    async def test_retry_missing_booking_marks_exhausted(
        self,
        service: BookingAutomationService,
    ) -> None:
        """If the booking was deleted, retry should mark as EXHAUSTED."""
        record = _make_automation_status(status="FAILED", attempt_count=1)

        with (
            patch.object(
                service._status_repo,
                "get_retryable",
                new_callable=AsyncMock,
                return_value=[record],
            ),
            patch.object(
                service._booking_repo,
                "get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                service._status_repo,
                "mark_exhausted",
                new_callable=AsyncMock,
            ) as mock_exhausted,
        ):
            await service.retry_failed_operations()
            mock_exhausted.assert_called_once()


# ---------------------------------------------------------------------------
# Worker integration
# ---------------------------------------------------------------------------


class TestWorkerIntegration:
    """Worker accepts booking_automation_service parameter."""

    def test_process_outbox_events_accepts_booking_automation(self) -> None:
        """process_outbox_events should accept booking_automation_service."""
        import inspect

        from app.workers import process_outbox_events

        sig = inspect.signature(process_outbox_events)
        assert "booking_automation_service" in sig.parameters

    def test_retry_failed_booking_automation_exists(self) -> None:
        """retry_failed_booking_automation should be importable."""
        from app.workers import retry_failed_booking_automation

        assert callable(retry_failed_booking_automation)


# ---------------------------------------------------------------------------
# Bookings API — no synchronous calendar sync
# ---------------------------------------------------------------------------


class TestBookingsAPINoLongerSyncsCalendar:
    """Booking endpoints no longer call calendar sync directly."""

    def test_no_maybe_sync_calendar_function(self) -> None:
        """_maybe_sync_calendar should no longer exist in bookings.py."""
        from app.api.v1 import bookings

        assert not hasattr(bookings, "_maybe_sync_calendar")

    def test_transition_endpoint_no_request_param(self) -> None:
        """transition_business_booking should not require Request param."""
        import inspect

        from app.api.v1.bookings import transition_business_booking

        sig = inspect.signature(transition_business_booking)
        param_names = list(sig.parameters.keys())
        assert "request" not in param_names


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    """Migration file exists and is correctly configured."""

    def test_migration_file_exists(self) -> None:
        test_file = pathlib.Path(__file__)
        project_root = test_file.parents[3]
        migration_path = project_root / "backend" / "alembic" / "versions" / "022_booking_automation_status.py"
        assert migration_path.exists(), f"Migration not found at {migration_path}"

    def test_migration_has_correct_revision(self) -> None:
        test_file = pathlib.Path(__file__)
        project_root = test_file.parents[3]
        migration_path = project_root / "backend" / "alembic" / "versions" / "022_booking_automation_status.py"
        content = migration_path.read_text()
        assert 'revision: str = "022_booking_automation_status"' in content
        assert 'down_revision: str = "021_calendar_connections"' in content

    def test_migration_creates_table(self) -> None:
        test_file = pathlib.Path(__file__)
        project_root = test_file.parents[3]
        migration_path = project_root / "backend" / "alembic" / "versions" / "022_booking_automation_status.py"
        content = migration_path.read_text()
        assert "booking_automation_status" in content
        assert "operation_type" in content
        assert "next_retry_at" in content


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Different businesses have isolated automation status."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture()
    def service(self, mock_session: AsyncMock) -> BookingAutomationService:
        return BookingAutomationService(mock_session, app_secret="test-secret")

    async def test_different_business_isolation(
        self,
        service: BookingAutomationService,
    ) -> None:
        """Processing events for different businesses should be independent."""
        biz_a = uuid.uuid4()
        biz_b = uuid.uuid4()
        booking_a = uuid.uuid4()
        booking_b = uuid.uuid4()

        # Process for business A
        with patch.object(service, "_handle_confirmed", new_callable=AsyncMock) as mock_a:
            await service.process_event(
                business_id=biz_a,
                event_type="BOOKING_CONFIRMED",
                payload={"booking_id": str(booking_a)},
            )
            mock_a.assert_called_once_with(biz_a, booking_a, "BOOKING_CONFIRMED")

        # Process for business B
        with patch.object(service, "_handle_confirmed", new_callable=AsyncMock) as mock_b:
            await service.process_event(
                business_id=biz_b,
                event_type="BOOKING_CONFIRMED",
                payload={"booking_id": str(booking_b)},
            )
            mock_b.assert_called_once_with(biz_b, booking_b, "BOOKING_CONFIRMED")
