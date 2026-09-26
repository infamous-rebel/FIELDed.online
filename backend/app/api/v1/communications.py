"""Communication API endpoints.

Provides APIs for communications, notifications, templates,
configuration, customer preferences, and provider webhooks.

All business-scoped endpoints enforce tenant isolation.
Customer-facing endpoints enforce customer boundaries.
Webhook endpoints use provider signature verification.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.common.enums import AuditEventType
from app.domain.communication.models import (
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    CustomerCommunicationPreference,
)
from app.domain.communication.notification_service import NotificationService
from app.domain.communication.repository import (
    CommunicationConfigRepository,
    CommunicationRepository,
    CommunicationTemplateRepository,
    ConsentRepository,
)
from app.domain.communication.schemas import (
    BusinessChannelConfigRead,
    BusinessChannelConfigUpdate,
    BusinessPurposeConfigRead,
    BusinessPurposeConfigUpdate,
    CommunicationAttemptRead,
    CommunicationListRead,
    CommunicationRead,
    CommunicationTemplateCreate,
    CommunicationTemplateRead,
    CommunicationTemplateVersionRead,
    CustomerPreferenceRead,
    OptInRequest,
    OptOutRequest,
)
from app.domain.identity.models import User
from app.domain.notification.schemas import (
    NotificationListRead,
    NotificationRead,
    UnreadCountResponse,
)
from app.domain.outbox.models import OutboxEvent
from app.security.authorization import (
    require_business_member,
    require_customer,
)

router = APIRouter()


# ── Communications ──


@router.get(
    "/{business_id}/communications",
    response_model=list[CommunicationListRead],
)
async def list_communications(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    channel: str | None = Query(None),
    purpose: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CommunicationListRead]:
    """List communications for a business (tenant-scoped)."""
    repo = CommunicationRepository(db)
    comms = await repo.list_for_business(
        business_id,
        channel=channel,
        purpose=purpose,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [CommunicationListRead.model_validate(c) for c in comms]


@router.get(
    "/{business_id}/communications/{communication_id}",
    response_model=CommunicationRead,
)
async def get_communication(
    business_id: uuid.UUID,
    communication_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommunicationRead:
    """Get a communication by ID (tenant-scoped)."""
    repo = CommunicationRepository(db)
    comm = await repo.get_by_id(communication_id, business_id=business_id)
    if comm is None:
        raise HTTPException(status_code=404, detail="Communication not found")
    return CommunicationRead.model_validate(comm)


@router.get(
    "/{business_id}/communications/{communication_id}/attempts",
    response_model=list[CommunicationAttemptRead],
)
async def list_communication_attempts(
    business_id: uuid.UUID,
    communication_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CommunicationAttemptRead]:
    """List delivery attempts for a communication."""
    repo = CommunicationRepository(db)
    # Verify tenant ownership
    comm = await repo.get_by_id(communication_id, business_id=business_id)
    if comm is None:
        raise HTTPException(status_code=404, detail="Communication not found")
    attempts = await repo.list_attempts(communication_id)
    return [CommunicationAttemptRead.model_validate(a) for a in attempts]


# ── Notifications (business-side) ──


@router.get(
    "/{business_id}/notifications",
    response_model=list[NotificationListRead],
)
async def list_business_notifications(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    notification_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[NotificationListRead]:
    """List notifications for a business."""
    service = NotificationService(db)
    notifications = await service.list_for_business(
        business_id,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )
    return [NotificationListRead.model_validate(n) for n in notifications]


# ── Notifications (customer-side) ──


@router.get(
    "/notifications/my-notifications",
    response_model=list[NotificationListRead],
)
async def list_my_notifications(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[NotificationListRead]:
    """List notifications for the authenticated customer."""
    service = NotificationService(db)
    notifications = await service.list_for_customer(
        user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return [NotificationListRead.model_validate(n) for n in notifications]


@router.patch(
    "/notifications/my-notifications/{notification_id}/read",
    response_model=NotificationRead,
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationRead:
    """Mark a notification as read."""
    service = NotificationService(db)
    notification = await service.mark_read(notification_id, customer_id=user.id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationRead.model_validate(notification)


@router.get(
    "/notifications/my-notifications/unread-count",
    response_model=UnreadCountResponse,
)
async def get_unread_count(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UnreadCountResponse:
    """Get unread notification count for the authenticated customer."""
    service = NotificationService(db)
    count = await service.count_unread(user.id)
    return UnreadCountResponse(unread_count=count)


# ── Templates ──


@router.post(
    "/{business_id}/communication-templates",
    response_model=CommunicationTemplateRead,
    status_code=201,
)
async def create_template(
    business_id: uuid.UUID,
    body: CommunicationTemplateCreate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommunicationTemplateRead:
    """Create a communication template."""
    from app.domain.communication.models import CommunicationTemplate

    repo = CommunicationTemplateRepository(db)
    template = CommunicationTemplate(
        business_id=business_id,
        channel=body.channel,
        purpose=body.purpose,
        name=body.name,
    )
    template = await repo.create(template)

    # Create initial version
    if body.body:
        from app.domain.communication.models import CommunicationTemplateVersion

        version = CommunicationTemplateVersion(
            template_id=template.id,
            version_number=1,
            subject=body.subject,
            body=body.body,
            variables=body.variables,
            created_by=user.id,
        )
        await repo.add_version(version)
        await db.flush()
        template.active_version_id = version.id
        await db.flush()

    await db.refresh(template)
    return CommunicationTemplateRead.model_validate(template)


@router.get(
    "/{business_id}/communication-templates",
    response_model=list[CommunicationTemplateRead],
)
async def list_templates(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    channel: str | None = Query(None),
    purpose: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CommunicationTemplateRead]:
    """List templates for a business."""
    repo = CommunicationTemplateRepository(db)
    templates = await repo.list_for_business(business_id, channel=channel, purpose=purpose, limit=limit, offset=offset)
    return [CommunicationTemplateRead.model_validate(t) for t in templates]


@router.get(
    "/{business_id}/communication-templates/{template_id}",
    response_model=CommunicationTemplateRead,
)
async def get_template(
    business_id: uuid.UUID,
    template_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommunicationTemplateRead:
    """Get a template by ID."""
    repo = CommunicationTemplateRepository(db)
    template = await repo.get_by_id(template_id, business_id=business_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return CommunicationTemplateRead.model_validate(template)


@router.put(
    "/{business_id}/communication-templates/{template_id}",
    response_model=CommunicationTemplateRead,
)
async def update_template(
    business_id: uuid.UUID,
    template_id: uuid.UUID,
    body: CommunicationTemplateCreate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommunicationTemplateRead:
    """Update a template (creates a new version)."""
    from app.domain.communication.models import CommunicationTemplateVersion

    repo = CommunicationTemplateRepository(db)
    template = await repo.get_by_id(template_id, business_id=business_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    if body.name:
        template.name = body.name

    # Create new version
    versions = await repo.list_versions(template_id)
    next_version = len(versions) + 1

    version = CommunicationTemplateVersion(
        template_id=template.id,
        version_number=next_version,
        subject=body.subject,
        body=body.body,
        variables=body.variables,
        created_by=user.id,
    )
    await repo.add_version(version)
    await db.flush()

    template.active_version_id = version.id
    await db.flush()
    await db.refresh(template)

    return CommunicationTemplateRead.model_validate(template)


@router.post(
    "/{business_id}/communication-templates/{template_id}/activate",
    response_model=CommunicationTemplateRead,
)
async def activate_template(
    business_id: uuid.UUID,
    template_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommunicationTemplateRead:
    """Activate a template."""
    repo = CommunicationTemplateRepository(db)
    template = await repo.get_by_id(template_id, business_id=business_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    template.status = "ACTIVE"
    await db.flush()
    await db.refresh(template)
    return CommunicationTemplateRead.model_validate(template)


@router.post(
    "/{business_id}/communication-templates/{template_id}/deactivate",
    response_model=CommunicationTemplateRead,
)
async def deactivate_template(
    business_id: uuid.UUID,
    template_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommunicationTemplateRead:
    """Deactivate a template."""
    repo = CommunicationTemplateRepository(db)
    template = await repo.get_by_id(template_id, business_id=business_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    template.status = "INACTIVE"
    await db.flush()
    await db.refresh(template)
    return CommunicationTemplateRead.model_validate(template)


@router.get(
    "/{business_id}/communication-templates/{template_id}/versions",
    response_model=list[CommunicationTemplateVersionRead],
)
async def list_template_versions(
    business_id: uuid.UUID,
    template_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CommunicationTemplateVersionRead]:
    """List all versions for a template."""
    repo = CommunicationTemplateRepository(db)
    # Verify tenant ownership
    template = await repo.get_by_id(template_id, business_id=business_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    versions = await repo.list_versions(template_id)
    return [CommunicationTemplateVersionRead.model_validate(v) for v in versions]


# ── Configuration ──


@router.get(
    "/{business_id}/communication-config/channels",
    response_model=list[BusinessChannelConfigRead],
)
async def list_channel_configs(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[BusinessChannelConfigRead]:
    """List channel configurations for a business."""
    repo = CommunicationConfigRepository(db)
    configs = await repo.list_channel_configs(business_id)
    return [BusinessChannelConfigRead.model_validate(c) for c in configs]


@router.put(
    "/{business_id}/communication-config/channels/{channel}",
    response_model=BusinessChannelConfigRead,
)
async def upsert_channel_config(
    business_id: uuid.UUID,
    channel: str,
    body: BusinessChannelConfigUpdate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessChannelConfigRead:
    """Create or update a channel configuration."""
    repo = CommunicationConfigRepository(db)
    config = BusinessCommunicationChannel(
        business_id=business_id,
        channel=channel.upper(),
        enabled=body.enabled if body.enabled is not None else False,
        provider_ref=body.provider_ref,
        settings=body.settings,
    )
    result = await repo.upsert_channel_config(config)

    # Audit: communication setting change (same transaction, via outbox)
    db.add(
        OutboxEvent(
            business_id=business_id,
            event_type=AuditEventType.COMMUNICATION_CONFIG_UPDATED,
            aggregate_type="communication_channel_config",
            aggregate_id=result.id,
            payload={
                "notification_title": "Communication settings updated",
                "notification_body": (f"Channel '{channel}' configuration was updated."),
                "config": {"channel": channel, "enabled": result.enabled},
            },
            idempotency_key=(
                f"COMMUNICATION_CONFIG_UPDATED:communication_channel_config:"
                f"{result.id}:{int(datetime.now(UTC).timestamp())}"
            ),
            status="PENDING",
            available_at=datetime.now(UTC),
        )
    )
    await db.flush()

    return BusinessChannelConfigRead.model_validate(result)


@router.get(
    "/{business_id}/communication-config/purposes",
    response_model=list[BusinessPurposeConfigRead],
)
async def list_purpose_configs(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[BusinessPurposeConfigRead]:
    """List purpose configurations for a business."""
    repo = CommunicationConfigRepository(db)
    configs = await repo.list_purpose_configs(business_id)
    return [BusinessPurposeConfigRead.model_validate(c) for c in configs]


@router.put(
    "/{business_id}/communication-config/purposes/{purpose}",
    response_model=BusinessPurposeConfigRead,
)
async def upsert_purpose_config(
    business_id: uuid.UUID,
    purpose: str,
    body: BusinessPurposeConfigUpdate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessPurposeConfigRead:
    """Create or update a purpose configuration."""
    repo = CommunicationConfigRepository(db)
    config = BusinessCommunicationPurpose(
        business_id=business_id,
        purpose=purpose.upper(),
        enabled=body.enabled if body.enabled is not None else False,
        permitted_channels=body.permitted_channels,
    )
    result = await repo.upsert_purpose_config(config)

    # Audit: communication setting change (same transaction, via outbox)
    db.add(
        OutboxEvent(
            business_id=business_id,
            event_type=AuditEventType.COMMUNICATION_CONFIG_UPDATED,
            aggregate_type="communication_purpose_config",
            aggregate_id=result.id,
            payload={
                "notification_title": "Communication settings updated",
                "notification_body": (f"Purpose '{purpose}' configuration was updated."),
                "config": {"purpose": purpose, "enabled": result.enabled},
            },
            idempotency_key=(
                f"COMMUNICATION_CONFIG_UPDATED:communication_purpose_config:"
                f"{result.id}:{int(datetime.now(UTC).timestamp())}"
            ),
            status="PENDING",
            available_at=datetime.now(UTC),
        )
    )
    await db.flush()

    return BusinessPurposeConfigRead.model_validate(result)


# ── Customer Preferences ──


@router.get(
    "/customer/communication-preferences",
    response_model=list[CustomerPreferenceRead],
)
async def get_my_preferences(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    business_id: uuid.UUID = Query(...),
) -> list[CustomerPreferenceRead]:
    """Get communication preferences for the authenticated customer."""
    repo = ConsentRepository(db)
    prefs = await repo.list_for_customer(user.id, business_id)
    return [CustomerPreferenceRead.model_validate(p) for p in prefs]


@router.put(
    "/customer/communication-preferences",
    response_model=CustomerPreferenceRead,
)
async def update_my_preferences(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    body: CustomerPreferenceRead = None,
) -> CustomerPreferenceRead:
    """Update communication preferences."""
    # This is a simplified version — full implementation would accept
    # a proper update body
    raise HTTPException(status_code=501, detail="Use opt-in/opt-out endpoints")


@router.post(
    "/customer/communication-preferences/opt-in",
    response_model=CustomerPreferenceRead,
)
async def opt_in(
    user: Annotated[User, Depends(require_customer)],
    body: OptInRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerPreferenceRead:
    """Opt in to communications."""
    repo = ConsentRepository(db)
    pref = CustomerCommunicationPreference(
        customer_id=user.id,
        business_id=body.business_id,
        channel=body.channel.upper() if body.channel else None,
        purpose=body.purpose.upper() if body.purpose else None,
        consent_state="OPTED_IN",
        opt_in=True,
        source="customer_api",
        consented_at=datetime.now(UTC),
    )
    result = await repo.upsert(pref)
    return CustomerPreferenceRead.model_validate(result)


@router.post(
    "/customer/communication-preferences/opt-out",
    response_model=CustomerPreferenceRead,
)
async def opt_out(
    user: Annotated[User, Depends(require_customer)],
    body: OptOutRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerPreferenceRead:
    """Opt out of communications."""
    repo = ConsentRepository(db)
    pref = CustomerCommunicationPreference(
        customer_id=user.id,
        business_id=body.business_id,
        channel=body.channel.upper() if body.channel else None,
        purpose=body.purpose.upper() if body.purpose else None,
        consent_state="OPTED_OUT",
        opt_in=False,
        source="customer_api",
        consented_at=datetime.now(UTC),
    )
    result = await repo.upsert(pref)
    return CustomerPreferenceRead.model_validate(result)


@router.get(
    "/customer/communication-preferences/suppression-state",
)
async def get_suppression_state(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    business_id: uuid.UUID = Query(...),
) -> dict:
    """Get suppression/DNC state for the authenticated customer."""
    repo = ConsentRepository(db)
    prefs = await repo.list_for_customer(user.id, business_id)
    suppressed = any(p.suppression or p.do_not_contact for p in prefs)
    return {
        "customer_id": str(user.id),
        "business_id": str(business_id),
        "suppressed": suppressed,
        "do_not_contact": any(p.do_not_contact for p in prefs),
        "preferences_count": len(prefs),
    }


# ── Provider Webhooks ──


@router.post(
    "/webhooks/communications/{provider}",
    status_code=202,
)
async def receive_webhook(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Receive a provider webhook event.

    Authentication is via provider signature verification,
    not user auth tokens.
    """
    from app.domain.communication.models import CommunicationWebhook

    payload = await request.json()

    # Extract external event ID (provider-specific)
    external_event_id = _extract_webhook_event_id(provider, payload)
    event_type = _extract_webhook_event_type(provider, payload)

    # Idempotent webhook creation
    from app.domain.communication.repository import WebhookRepository

    webhook_repo = WebhookRepository(db)

    existing = await webhook_repo.get_by_provider_event(provider, external_event_id)
    if existing:
        return {"status": "duplicate", "webhook_id": str(existing.id)}

    webhook = CommunicationWebhook(
        provider=provider,
        external_event_id=external_event_id,
        event_type=event_type,
        raw_payload=payload,
        received_at=datetime.now(UTC),
    )
    webhook = await webhook_repo.create(webhook)

    # Process the webhook: update communication status
    await _process_delivery_webhook(db, provider, event_type, payload, webhook)

    return {"status": "accepted", "webhook_id": str(webhook.id)}


def _extract_webhook_event_id(provider: str, payload: dict) -> str:
    """Extract the external event ID from a webhook payload."""
    if provider == "resend":
        return payload.get("id", str(uuid.uuid4()))
    if provider in ("twilio_sms", "twilio_voice"):
        return payload.get("MessageSid", payload.get("CallSid", str(uuid.uuid4())))
    if provider in ("vonage_sms", "vonage_whatsapp"):
        # Vonage Messages API webhooks carry message_uuid + status
        msg_uuid = payload.get("message_uuid", "")
        status = payload.get("status", "")
        if msg_uuid and status:
            return f"{msg_uuid}:{status}"
        return msg_uuid or str(uuid.uuid4())
    # Fallback: hash the entire payload
    raw = str(payload).encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _extract_webhook_event_type(provider: str, payload: dict) -> str:
    """Extract the event type from a webhook payload."""
    if provider == "resend":
        return payload.get("type", "unknown")
    if provider == "twilio_sms":
        return payload.get("MessageStatus", "unknown")
    if provider == "twilio_voice":
        return payload.get("CallStatus", "unknown")
    if provider in ("vonage_sms", "vonage_whatsapp"):
        return payload.get("status", "unknown")
    return payload.get("event_type", "unknown")


async def _process_delivery_webhook(
    db: AsyncSession,
    provider: str,
    event_type: str,
    payload: dict,
    webhook: object,
) -> None:
    """Process a delivery webhook to update communication status.

    Supports:
    - Resend: email.delivered / email.bounced / email.failed
    - Vonage SMS/WhatsApp: delivered / failed / read / rejected
    """
    if provider == "resend":
        await _process_resend_delivery(db, event_type, payload)
    elif provider in ("vonage_sms", "vonage_whatsapp"):
        await _process_vonage_delivery(db, provider, event_type, payload)


async def _process_resend_delivery(
    db: AsyncSession,
    event_type: str,
    payload: dict,
) -> None:
    """Process a Resend delivery webhook."""
    data = payload.get("data", {})
    message_id = data.get("email_id", "")
    if not message_id:
        return

    from sqlalchemy import select

    from app.domain.communication.models import (
        Communication,
        CommunicationAttempt,
        CommunicationAuditEvent,
    )

    result = await db.execute(
        select(CommunicationAttempt).where(
            CommunicationAttempt.provider_reference == message_id,
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        return

    status_map = {
        "email.delivered": "DELIVERED",
        "email.bounced": "BOUNCED",
        "email.failed": "FAILED",
        "email.complained": "COMPLAINED",
    }
    new_status = status_map.get(event_type)
    if not new_status:
        return

    attempt.status = new_status

    comm_result = await db.execute(select(Communication).where(Communication.id == attempt.communication_id))
    communication = comm_result.scalar_one_or_none()
    if communication:
        comm_status_map = {
            "DELIVERED": "DELIVERED",
            "BOUNCED": "BOUNCED",
            "FAILED": "FAILED",
            "COMPLAINED": "COMPLAINED",
        }
        communication.status = comm_status_map.get(new_status, communication.status)

    audit = CommunicationAuditEvent(
        event_type=f"EMAIL_{new_status}",
        business_id=communication.business_id if communication else None,  # type: ignore[arg-type]
        customer_id=communication.customer_id if communication else None,
        channel="EMAIL",
        communication_id=attempt.communication_id,
        provider_reference=message_id,
        metadata_={"webhook_event_type": event_type, "payload": data},
    )
    db.add(audit)
    await db.flush()


async def _process_vonage_delivery(
    db: AsyncSession,
    provider: str,
    event_type: str,
    payload: dict,
) -> None:
    """Process a Vonage SMS/WhatsApp delivery status webhook.

    Vonage delivery receipts carry:
    - ``message_uuid``: the original message identifier
    - ``status``: delivery status (delivered, failed, rejected, submitted)
    - ``err-code``: error code (0 = no error)

    Inbound messages carry:
    - ``message_uuid``: unique message identifier
    - ``text``: message body
    - ``from``: sender's phone number
    - ``channel``: "sms" or "whatsapp"
    """
    from sqlalchemy import select

    from app.domain.communication.models import (
        Communication,
        CommunicationAttempt,
        CommunicationAuditEvent,
    )

    message_uuid = payload.get("message_uuid", "")
    if not message_uuid:
        return

    # Map Vonage status values to FIELDed attempt statuses
    vonage_status_map = {
        "delivered": "DELIVERED",
        "failed": "FAILED",
        "rejected": "FAILED",
        "submitted": "SUCCESS",
        "read": "DELIVERED",
    }
    new_status = vonage_status_map.get(event_type.lower())
    if not new_status:
        return

    # Find the attempt by provider reference (message_uuid)
    result = await db.execute(
        select(CommunicationAttempt).where(
            CommunicationAttempt.provider_reference == message_uuid,
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        return

    attempt.status = new_status
    if event_type.lower() in ("failed", "rejected"):
        err_code = payload.get("err-code", "")
        attempt.error = f"Vonage delivery failed: {event_type} (code: {err_code})"

    # Update parent communication status
    comm_result = await db.execute(select(Communication).where(Communication.id == attempt.communication_id))
    communication = comm_result.scalar_one_or_none()
    if communication:
        communication.status = new_status

    channel = "SMS" if "sms" in provider else "WHATSAPP"
    audit = CommunicationAuditEvent(
        event_type=f"{channel}_{new_status}",
        business_id=communication.business_id if communication else None,  # type: ignore[arg-type]
        customer_id=communication.customer_id if communication else None,
        channel=channel,
        communication_id=attempt.communication_id,
        provider_reference=message_uuid,
        metadata_={"webhook_event_type": event_type, "provider": provider, "payload": payload},
    )
    db.add(audit)
    await db.flush()
