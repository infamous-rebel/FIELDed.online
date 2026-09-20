"""Communication Orchestration Service.

Translates operational events (outbox events) into governed
communication through the full pipeline:

1. Create notification(s)
2. Resolve RecipientContext
3. Determine channel + purpose
4. Resolve + render template
5. Evaluate Communication Policy
6. If ALLOW: execute through provider adapter
7. Persist result + audit evidence

Idempotency key format:
    {event_type}:{aggregate_type}:{aggregate_id}:{channel}:{purpose}
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.common import ProviderResult
from app.adapters.email.base import EmailMessage, EmailProvider
from app.adapters.push.base import PushMessage, PushProvider
from app.adapters.sms.base import SMSMessage, SMSProvider
from app.adapters.voice.base import VoiceCallRequest, VoiceProvider
from app.adapters.whatsapp.base import WhatsAppMessage, WhatsAppProvider
from app.domain.communication.models import (
    Communication,
    CommunicationAttempt,
    CommunicationAuditEvent,
    CommunicationRecipient,
)
from app.domain.communication.policy import (
    CommunicationPolicyService,
    PolicyDecision,
    RecipientContext,
)
from app.domain.communication.repository import (
    AuditRepository,
    CommunicationRepository,
    CommunicationTemplateRepository,
)
from app.domain.notification.models import Notification
from app.domain.notification.repository import NotificationRepository

logger = logging.getLogger(__name__)

# Template variable pattern: {{ variable_name }}
_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class OrchestrationService:
    """Orchestrates the full communication pipeline.

    Receives outbox event payloads and produces governed
    communications through provider adapters.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        email_provider: EmailProvider,
        sms_provider: SMSProvider,
        voice_provider: VoiceProvider,
        whatsapp_provider: WhatsAppProvider,
        push_provider: PushProvider,
    ) -> None:
        self.session = session
        self.email_provider = email_provider
        self.sms_provider = sms_provider
        self.voice_provider = voice_provider
        self.whatsapp_provider = whatsapp_provider
        self.push_provider = push_provider

        self.comm_repo = CommunicationRepository(session)
        self.template_repo = CommunicationTemplateRepository(session)
        self.notification_repo = NotificationRepository(session)
        self.audit_repo = AuditRepository(session)
        self.policy_service = CommunicationPolicyService(session)

    async def process_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
        outbox_event_id: uuid.UUID,
    ) -> list[Communication]:
        """Process an outbox event into governed communications.

        Returns the list of Communication records created.
        """
        # Extract communication targets from payload
        targets = payload.get("communication_targets", [])
        if not targets:
            # Create a notification only (no external communication)
            await self._create_notification(
                business_id=business_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload,
                outbox_event_id=outbox_event_id,
            )
            return []

        communications: list[Communication] = []

        for target in targets:
            channel = target.get("channel", "")
            purpose = target.get("purpose", "")
            customer_id_str = target.get("customer_id")
            customer_id = uuid.UUID(customer_id_str) if customer_id_str else None
            recipient_address = target.get("recipient_address", "")
            recipient_type = target.get("recipient_type", "CUSTOMER")

            # Build idempotency key
            idempotency_key = f"{event_type}:{aggregate_type}:{aggregate_id}:{channel}:{purpose}"

            # Check idempotency
            existing = await self.comm_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                communications.append(existing)
                continue

            # Build recipient context
            recipient = RecipientContext(
                recipient_type=recipient_type,
                customer_id=customer_id,
                address=recipient_address,
                channel=channel,
                purpose=purpose,
            )

            # Create notification
            await self._create_notification(
                business_id=business_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload,
                outbox_event_id=outbox_event_id,
                customer_id=customer_id,
                notification_type=event_type,
            )

            # Evaluate policy
            decision = await self.policy_service.evaluate(
                business_id=business_id,
                recipient=recipient,
            )

            if not decision.is_allowed:
                # Audit the denial
                await self._audit_decision(
                    business_id=business_id,
                    customer_id=customer_id,
                    channel=channel,
                    purpose=purpose,
                    decision=decision,
                    event_type=event_type,
                )
                continue

            # Resolve and render template
            subject, body = await self._resolve_and_render_template(
                business_id=business_id,
                channel=channel,
                purpose=purpose,
                variables=payload.get("template_variables", {}),
            )

            # Execute communication
            communication = await self._execute_communication(
                business_id=business_id,
                customer_id=customer_id,
                channel=channel,
                purpose=purpose,
                idempotency_key=idempotency_key,
                recipient_address=recipient_address,
                recipient_type=recipient_type,
                subject=subject,
                body=body,
                decision=decision,
                payload=payload,
            )
            communications.append(communication)

        return communications

    async def _create_notification(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
        outbox_event_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        notification_type: str | None = None,
    ) -> Notification:
        """Create an idempotent notification."""
        idem_key = f"notification:{event_type}:{aggregate_type}:{aggregate_id}:{outbox_event_id}"
        title = payload.get("notification_title", event_type)
        body = payload.get("notification_body", f"Event: {event_type}")

        existing = await self.notification_repo.get_by_idempotency_key(idem_key)
        if existing:
            return existing

        notification = Notification(
            business_id=business_id,
            customer_id=customer_id,
            notification_type=notification_type or event_type,
            title=title,
            body=body,
            idempotency_key=idem_key,
            related_entity_type=aggregate_type,
            related_entity_id=aggregate_id,
        )
        return await self.notification_repo.create(notification)

    async def _resolve_and_render_template(
        self,
        *,
        business_id: uuid.UUID,
        channel: str,
        purpose: str,
        variables: dict,
    ) -> tuple[str | None, str]:
        """Resolve the active template and render it with variables.

        Returns (subject, body).  Subject may be None for non-email channels.
        Falls back to a basic body if no template is found.
        """
        # Find templates matching channel + purpose
        templates = await self.template_repo.list_for_business(
            business_id, channel=channel, purpose=purpose, limit=1
        )

        if not templates:
            # No template — use variables directly
            body = variables.get("body", "")
            subject = variables.get("subject")
            return subject, body

        template = templates[0]
        if template.active_version_id is None:
            body = variables.get("body", "")
            subject = variables.get("subject")
            return subject, body

        version = await self.template_repo.get_version(template.active_version_id)
        if version is None:
            body = variables.get("body", "")
            subject = variables.get("subject")
            return subject, body

        # Render template with deterministic variable substitution
        subject = _render_template(version.subject or "", variables)
        body = _render_template(version.body, variables)

        return subject, body

    async def _execute_communication(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID | None,
        channel: str,
        purpose: str,
        idempotency_key: str,
        recipient_address: str,
        recipient_type: str,
        subject: str | None,
        body: str,
        decision: PolicyDecision,
        payload: dict,
    ) -> Communication:
        """Create communication record and execute through provider."""
        # Create communication record
        communication = Communication(
            business_id=business_id,
            customer_id=customer_id,
            channel=channel,
            purpose=purpose,
            status="PENDING",
            idempotency_key=idempotency_key,
            brain_version_id=decision.brain_version_id,
            decision_evidence=decision.to_evidence_dict(),
            enquiry_id=_parse_uuid(payload.get("enquiry_id")),
            quote_id=_parse_uuid(payload.get("quote_id")),
            booking_id=_parse_uuid(payload.get("booking_id")),
            service_execution_id=_parse_uuid(payload.get("service_execution_id")),
            invoice_id=_parse_uuid(payload.get("invoice_id")),
        )
        communication = await self.comm_repo.create(communication)

        # Create recipient
        recipient = CommunicationRecipient(
            communication_id=communication.id,
            recipient_type=recipient_type,
            channel=channel,
            address=recipient_address,
            status="PENDING",
        )
        await self.comm_repo.add_recipient(recipient)

        # Create attempt
        attempt = CommunicationAttempt(
            communication_id=communication.id,
            provider_name=self._get_provider_name(channel),
            status="PENDING",
        )
        attempt = await self.comm_repo.add_attempt(attempt)

        # Execute provider call (no DB lock held)
        result = await self._invoke_provider(
            channel=channel,
            address=recipient_address,
            subject=subject,
            body=body,
        )

        # Persist result
        if result.success:
            attempt.status = "SUCCESS"
            attempt.provider_reference = result.provider_reference
            attempt.provider_response = result.raw_response
            communication.status = "SENT"
            communication.provider_reference = result.provider_reference
            recipient.status = "SENT"
        else:
            attempt.status = "FAILED" if not result.retryable else "RETRYABLE"
            attempt.error = result.error
            attempt.provider_response = result.raw_response
            communication.status = "FAILED"
            recipient.status = "FAILED"

        await self.session.flush()

        # Audit
        audit_event_type = "COMMUNICATION_SENT" if result.success else "COMMUNICATION_FAILED"
        audit = CommunicationAuditEvent(
            event_type=audit_event_type,
            business_id=business_id,
            customer_id=customer_id,
            channel=channel,
            purpose=purpose,
            communication_id=communication.id,
            brain_version_id=decision.brain_version_id,
            decision_evidence=decision.to_evidence_dict(),
            provider_reference=result.provider_reference,
        )
        await self.audit_repo.create(audit)

        return communication

    async def _invoke_provider(
        self,
        *,
        channel: str,
        address: str,
        subject: str | None,
        body: str,
    ) -> ProviderResult:
        """Invoke the appropriate provider adapter."""
        if channel == "EMAIL":
            msg = EmailMessage(
                to=address,
                subject=subject or "",
                body=body,
            )
            return await self.email_provider.send(msg)

        if channel == "SMS":
            msg = SMSMessage(to=address, body=body)
            return await self.sms_provider.send(msg)

        if channel == "VOICE":
            req = VoiceCallRequest(to=address, from_number="")
            return await self.voice_provider.initiate_call(req)

        if channel == "WHATSAPP":
            msg = WhatsAppMessage(to=address, body=body)
            return await self.whatsapp_provider.send(msg)

        if channel == "PUSH":
            msg = PushMessage(
                device_token=address,
                title=subject or "",
                body=body,
            )
            return await self.push_provider.send(msg)

        return ProviderResult.failure(
            error=f"Unsupported channel: {channel}",
            retryable=False,
        )

    def _get_provider_name(self, channel: str) -> str:
        """Get the provider name for a channel."""
        providers = {
            "EMAIL": self.email_provider.provider_name,
            "SMS": self.sms_provider.provider_name,
            "VOICE": self.voice_provider.provider_name,
            "WHATSAPP": self.whatsapp_provider.provider_name,
            "PUSH": self.push_provider.provider_name,
        }
        return providers.get(channel, "unknown")

    async def _audit_decision(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID | None,
        channel: str,
        purpose: str,
        decision: PolicyDecision,
        event_type: str,
    ) -> None:
        """Audit a policy decision that blocked communication."""
        event_type_map = {
            "DENY": "COMMUNICATION_DENIED",
            "REQUIRE_APPROVAL": "COMMUNICATION_DEFERRED",
            "DEFER": "COMMUNICATION_DEFERRED",
            "ESCALATE": "COMMUNICATION_DEFERRED",
        }
        audit = CommunicationAuditEvent(
            event_type=event_type_map.get(decision.decision, "COMMUNICATION_DENIED"),
            business_id=business_id,
            customer_id=customer_id,
            channel=channel,
            purpose=purpose,
            brain_version_id=decision.brain_version_id,
            decision_evidence=decision.to_evidence_dict(),
        )
        await self.audit_repo.create(audit)


def _render_template(template: str, variables: dict) -> str:
    """Render a template string with variable substitution.

    Replaces {{ variable_name }} with the corresponding value
    from the variables dict.  Unknown variables are left as-is.
    """

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = variables.get(var_name)
        if value is not None:
            return str(value)
        return match.group(0)  # Leave unknown variables as-is

    return _TEMPLATE_VAR_RE.sub(replacer, template)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    """Safely parse a UUID string."""
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None
