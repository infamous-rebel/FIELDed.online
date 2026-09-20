"""Phase 14B voice outbox integration.

Voice domain events flow through the transactional outbox:  the event
is inserted in the SAME session/transaction as the state change it
describes, and the outbox worker delivers it asynchronously.

Delivery for ``voice.*`` events is limited to idempotent in-app
notifications.  A voice call is itself the communication channel —
voice events must never trigger provider calls.

Event types:
    voice.call_initiated        — a dial succeeded
    voice.call_completed        — the call reached COMPLETED
    voice.call_failed           — the call reached FAILED
    voice.escalation_requested  — the call was escalated to a human
    voice.campaign_completed    — a campaign auto-completed
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notification.models import Notification
from app.domain.notification.repository import NotificationRepository
from app.domain.outbox.models import OutboxEvent
from app.domain.outbox.repository import OutboxRepository

logger = logging.getLogger(__name__)

VOICE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "voice.call_initiated",
        "voice.call_completed",
        "voice.call_failed",
        "voice.escalation_requested",
        "voice.campaign_completed",
    }
)

_NOTIFICATION_TITLES: dict[str, str] = {
    "voice.call_initiated": "Voice call initiated",
    "voice.call_completed": "Voice call completed",
    "voice.call_failed": "Voice call failed",
    "voice.escalation_requested": "Voice call escalated to a human",
    "voice.campaign_completed": "Voice campaign completed",
}


def _notification_text(event_type: str, payload: dict) -> tuple[str, str]:
    """Deterministic notification title/body for a voice event."""
    title = payload.get("notification_title") or _NOTIFICATION_TITLES.get(
        event_type, event_type
    )
    body = payload.get("notification_body") or f"Voice event: {event_type}"
    return str(title), str(body)


async def emit_voice_event(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict | None = None,
    slot: str = "",
) -> OutboxEvent | None:
    """Emit a voice domain event through the transactional outbox.

    The event row is added to the caller's current transaction — the
    state change and its event commit atomically (the worker handles
    delivery later).  ``slot`` disambiguates multiple emissions for
    the same aggregate (e.g. one dial attempt each); an empty slot
    yields one event per (event_type, aggregate_id) pair.

    Re-emission with the same idempotency key is a no-op returning
    ``None``.
    """
    if event_type not in VOICE_EVENT_TYPES:
        raise ValueError(f"Unknown voice event type: '{event_type}'")

    repo = OutboxRepository(session)
    idem_key = f"voice:{event_type}:{aggregate_id}:{slot}"
    if await repo.get_by_idempotency_key(idem_key) is not None:
        return None

    event = OutboxEvent(
        business_id=business_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        idempotency_key=idem_key,
        status="PENDING",
        available_at=datetime.now(UTC),
    )
    event = await repo.create(event)
    logger.info(
        "voice_outbox_event_emitted",
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        outbox_event_id=str(event.id),
    )
    return event


class VoiceEventOrchestrator:
    """Delivers voice outbox events as idempotent in-app notifications.

    Voice events never trigger provider calls — the call itself is
    the communication.  A notification per outbox event is the only
    side effect, keyed ``notification:{outbox_event_id}`` so worker
    replays never duplicate.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notification_repo = NotificationRepository(session)

    async def process_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
        outbox_event_id: uuid.UUID,
    ) -> None:
        idem_key = f"notification:{outbox_event_id}"
        existing = await self.notification_repo.get_by_idempotency_key(idem_key)
        if existing is not None:
            return

        title, body = _notification_text(event_type, payload)
        customer_id_str = payload.get("customer_id")
        notification = Notification(
            business_id=business_id,
            customer_id=(
                uuid.UUID(customer_id_str) if customer_id_str else None
            ),
            notification_type=event_type,
            title=title,
            body=body,
            idempotency_key=idem_key,
            related_entity_type=aggregate_type,
            related_entity_id=aggregate_id,
        )
        await self.notification_repo.create(notification)
        logger.info(
            "voice_event_notification_created",
            event_type=event_type,
            outbox_event_id=str(outbox_event_id),
        )
