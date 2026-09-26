"""Outbox event processor.

The single source of worker logic for processing outbox events.
Callable from both FastAPI background tasks and standalone CLI.

Concurrency model:
- Claim events with SELECT ... FOR UPDATE SKIP LOCKED
- Commit the claim transaction (status → PROCESSING)
- Release DB lock before external I/O
- Process each event through the orchestration service
- Update status in a separate transaction

Booking automation:
- BOOKING_* events also trigger downstream automation (calendar sync,
  service execution creation, payment prep) via BookingAutomationService.
- Automation failures are tracked independently and do NOT affect the
  outbox event status — communication/notifications always succeed.
- Failed operations are retried via retry_failed_booking_automation().
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.communication.orchestration import OrchestrationService
from app.domain.outbox.repository import OutboxRepository
from app.domain.voice.outbox_integration import VoiceEventOrchestrator

logger = logging.getLogger(__name__)

# Booking event types that trigger downstream automation.
_BOOKING_AUTOMATION_EVENTS = frozenset(
    {
        "BOOKING_CONFIRMED",
        "BOOKING_CANCELLED",
        "BOOKING_COMPLETED",
        "BOOKING_IN_PROGRESS",
    }
)


async def process_outbox_events(
    session: AsyncSession,
    *,
    orchestrator: OrchestrationService,
    batch_size: int = 10,
    lease_seconds: int = 300,
    max_attempts: int = 5,
    voice_orchestrator: VoiceEventOrchestrator | None = None,
    booking_automation_service: object | None = None,
) -> int:
    """Process pending outbox events.

    Claims a batch of pending/retryable events, processes each
    through the orchestration service, and updates their status.

    ``voice.*`` events route to the voice orchestrator (idempotent
    in-app notifications only); every other event type goes to the
    Phase 14A communication orchestrator, whose behavior is unchanged
    when ``voice_orchestrator`` is omitted and no voice events exist.

    When ``booking_automation_service`` is provided, BOOKING_* events
    also trigger downstream automation (calendar sync, service execution,
    payment prep).  Automation failures are tracked independently and
    do NOT affect the outbox event status — communication/notifications
    always succeed even if automation fails.

    Returns the number of events successfully processed.
    """
    repo = OutboxRepository(session)

    # Claim events (FOR UPDATE SKIP LOCKED + lease recovery)
    events = await repo.claim_pending_events(
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )

    if not events:
        return 0

    # Commit the claim transaction to release row locks
    await session.commit()

    processed = 0

    for event in events:
        try:
            # Process through orchestration — voice.* events route to
            # the voice orchestrator, everything else to 14A.
            if event.event_type.startswith("voice."):
                if voice_orchestrator is None:
                    raise RuntimeError("voice outbox event encountered but no voice orchestrator is configured")
                await voice_orchestrator.process_event(
                    business_id=event.business_id,
                    event_type=event.event_type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.payload or {},
                    outbox_event_id=event.id,
                )
            else:
                await orchestrator.process_event(
                    business_id=event.business_id,
                    event_type=event.event_type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.payload or {},
                    outbox_event_id=event.id,
                )

            # Booking automation: best-effort downstream operations.
            # Runs AFTER communication orchestration so that notification
            # delivery is never blocked by automation failures.
            if (
                booking_automation_service is not None
                and event.aggregate_type == "booking"
                and event.event_type in _BOOKING_AUTOMATION_EVENTS
            ):
                try:
                    await booking_automation_service.process_event(
                        business_id=event.business_id,
                        event_type=event.event_type,
                        payload=event.payload or {},
                    )
                except Exception:
                    # Automation failure is tracked in booking_automation_status.
                    # It does NOT affect the outbox event status.
                    logger.warning(
                        "booking_automation_failed_during_outbox_processing",
                        event_id=str(event.id),
                        event_type=event.event_type,
                        exc_info=True,
                    )

            # Mark processed
            await repo.mark_processed(event.id)
            await session.commit()
            processed += 1

            logger.info(
                "Outbox event processed: %s:%s:%s",
                event.event_type,
                event.aggregate_type,
                event.aggregate_id,
            )

        except Exception as exc:
            logger.exception("Failed to process outbox event %s", event.id)

            # Roll back any partial state from orchestration
            await session.rollback()

            # Update event status
            if event.attempt_count >= max_attempts:
                await repo.mark_failed(event.id, error=str(exc)[:1000])
                logger.error(
                    "Outbox event %s permanently failed after %d attempts",
                    event.id,
                    event.attempt_count,
                )
            else:
                await repo.mark_retryable(event.id, error=str(exc)[:1000])

            try:
                await session.commit()
            except Exception:
                logger.exception(
                    "Failed to commit error status for event %s",
                    event.id,
                )
                await session.rollback()

    return processed


async def retry_failed_booking_automation(
    session: AsyncSession,
    *,
    app_secret: str = "",
) -> int:
    """Retry failed booking automation operations.

    Independent retry loop for downstream operations that failed
    during outbox event processing.  Each operation is retried
    independently with its own attempt tracking.

    Returns the number of operations successfully retried.
    """
    from app.domain.booking_automation.service import BookingAutomationService

    service = BookingAutomationService(session, app_secret=app_secret)
    return await service.retry_failed_operations()
