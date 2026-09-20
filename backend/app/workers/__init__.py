"""Outbox event processor.

The single source of worker logic for processing outbox events.
Callable from both FastAPI background tasks and standalone CLI.

Concurrency model:
- Claim events with SELECT ... FOR UPDATE SKIP LOCKED
- Commit the claim transaction (status → PROCESSING)
- Release DB lock before external I/O
- Process each event through the orchestration service
- Update status in a separate transaction
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.communication.orchestration import OrchestrationService
from app.domain.outbox.repository import OutboxRepository
from app.domain.voice.outbox_integration import VoiceEventOrchestrator

logger = logging.getLogger(__name__)


async def process_outbox_events(
    session: AsyncSession,
    *,
    orchestrator: OrchestrationService,
    batch_size: int = 10,
    lease_seconds: int = 300,
    max_attempts: int = 5,
    voice_orchestrator: VoiceEventOrchestrator | None = None,
) -> int:
    """Process pending outbox events.

    Claims a batch of pending/retryable events, processes each
    through the orchestration service, and updates their status.

    ``voice.*`` events route to the voice orchestrator (idempotent
    in-app notifications only); every other event type goes to the
    Phase 14A communication orchestrator, whose behavior is unchanged
    when ``voice_orchestrator`` is omitted and no voice events exist.

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
                    raise RuntimeError(
                        "voice outbox event encountered but no voice orchestrator is configured"
                    )
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
