"""Transactional email notification service.

The single entry point for sending lifecycle emails from FIELDed.

Flow:
    Outbox event
    → EmailNotificationService.process_event()
    → Resolve recipients (customer email, business member emails)
    → Select template from registry
    → Render with real FIELDed data
    → Send through EmailProvider adapter
    → Persist Communication + attempt records
    → Return result (failure-safe — never raises)

A notification failure does NOT roll back a successful business
transaction.  All errors are caught, logged, and persisted as
failed communication attempts.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.email.base import EmailMessage, EmailProvider
from app.domain.communication.models import (
    Communication,
    CommunicationAttempt,
    CommunicationAuditEvent,
    CommunicationRecipient,
)
from app.domain.communication.repository import (
    AuditRepository,
    CommunicationRepository,
)
from app.domain.notification.email_templates import (
    BUSINESS_TEMPLATES,
    CUSTOMER_TEMPLATES,
    EmailTemplate,
    resolve_event_type,
)

logger = logging.getLogger(__name__)

_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class EmailNotificationService:
    """Sends transactional emails for FIELDed lifecycle events.

    This service is called by the outbox worker for each event.
    It resolves recipients, renders templates, sends through the
    email provider, and persists audit records.

    All errors are caught and logged — a notification failure
    never propagates to the caller.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        email_provider: EmailProvider,
        from_address: str = "noreply@fielded.online",
        reply_to: str | None = None,
    ) -> None:
        self.session = session
        self.email_provider = email_provider
        self.from_address = from_address
        self.reply_to = reply_to
        self.comm_repo = CommunicationRepository(session)
        self.audit_repo = AuditRepository(session)

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
        """Process an outbox event into transactional emails.

        Sends emails to the customer and/or business members as
        appropriate for the event type.

        Returns the list of Communication records created.
        Failures are caught and logged — this method never raises.
        """
        try:
            return await self._process_event_inner(
                business_id=business_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload,
                outbox_event_id=outbox_event_id,
            )
        except Exception:
            logger.exception(
                "email_notification_failed: %s:%s:%s",
                event_type,
                aggregate_type,
                aggregate_id,
            )
            return []

    async def _process_event_inner(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
        outbox_event_id: uuid.UUID,
    ) -> list[Communication]:
        """Inner processing — exceptions propagate to the outer catch."""
        notification_event_type = resolve_event_type(event_type)
        communications: list[Communication] = []

        # Resolve shared template variables from domain
        variables = await self._resolve_variables(
            business_id=business_id,
            payload=payload,
        )

        # ── Customer email ────────────────────────────────────────────
        customer_template = CUSTOMER_TEMPLATES.get(notification_event_type)
        customer_id = _parse_uuid(payload.get("customer_id"))

        if customer_template and customer_id:
            customer_email = await self._resolve_customer_email(customer_id)
            if customer_email:
                comm = await self._send_email(
                    template=customer_template,
                    variables=variables,
                    recipient_email=customer_email,
                    recipient_type="CUSTOMER",
                    business_id=business_id,
                    customer_id=customer_id,
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    outbox_event_id=outbox_event_id,
                    payload=payload,
                )
                if comm:
                    communications.append(comm)

        # ── Business email ────────────────────────────────────────────
        business_template = BUSINESS_TEMPLATES.get(notification_event_type)
        if business_template:
            business_emails = await self._resolve_business_emails(business_id)
            for email_addr in business_emails:
                comm = await self._send_email(
                    template=business_template,
                    variables=variables,
                    recipient_email=email_addr,
                    recipient_type="BUSINESS_MEMBER",
                    business_id=business_id,
                    customer_id=customer_id,
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    outbox_event_id=outbox_event_id,
                    payload=payload,
                )
                if comm:
                    communications.append(comm)

        return communications

    async def _send_email(
        self,
        *,
        template: EmailTemplate,
        variables: dict,
        recipient_email: str,
        recipient_type: str,
        business_id: uuid.UUID,
        customer_id: uuid.UUID | None,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        outbox_event_id: uuid.UUID,
        payload: dict,
    ) -> Communication | None:
        """Render and send a single email, persisting all records."""
        # Build idempotency key with recipient discriminator
        recipient_suffix = f"cust:{customer_id}" if customer_id else "biz"
        idempotency_key = (
            f"email:{event_type}:{aggregate_type}:{aggregate_id}:{recipient_type}:{recipient_suffix}:{outbox_event_id}"
        )

        # Check idempotency
        existing = await self.comm_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Render template
        subject = _render(template.subject, variables)
        html_body = _render(template.body, variables)

        # Create communication record
        communication = Communication(
            business_id=business_id,
            customer_id=customer_id,
            channel="EMAIL",
            purpose=template.event_type,
            status="PENDING",
            idempotency_key=idempotency_key,
            enquiry_id=_parse_uuid(payload.get("enquiry_id")),
            quote_id=_parse_uuid(payload.get("quote_id")),
            booking_id=_parse_uuid(payload.get("booking_id")),
            service_execution_id=_parse_uuid(payload.get("service_execution_id")),
            invoice_id=_parse_uuid(payload.get("invoice_id")),
        )
        communication = await self.comm_repo.create(communication)

        # Create recipient record
        recipient = CommunicationRecipient(
            communication_id=communication.id,
            recipient_type=recipient_type,
            channel="EMAIL",
            address=recipient_email,
            status="PENDING",
        )
        await self.comm_repo.add_recipient(recipient)

        # Create attempt record
        attempt = CommunicationAttempt(
            communication_id=communication.id,
            provider_name=self.email_provider.provider_name,
            status="PENDING",
        )
        attempt = await self.comm_repo.add_attempt(attempt)

        # Send through provider
        message = EmailMessage(
            to=recipient_email,
            subject=subject,
            body=html_body,
            html_body=html_body,
            from_address=self.from_address,
            reply_to=self.reply_to,
        )

        result = await self.email_provider.send(message)

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
            channel="EMAIL",
            purpose=template.event_type,
            communication_id=communication.id,
            provider_reference=result.provider_reference,
        )
        await self.audit_repo.create(audit)

        if result.success:
            logger.info(
                "email_sent: %s → %s (ref=%s)",
                template.event_type,
                recipient_email,
                result.provider_reference,
            )
        else:
            logger.warning(
                "email_failed: %s → %s error=%s retryable=%s",
                template.event_type,
                recipient_email,
                result.error,
                result.retryable,
            )

        return communication

    # ── Variable resolution ──────────────────────────────────────────────

    async def _resolve_variables(
        self,
        *,
        business_id: uuid.UUID,
        payload: dict,
    ) -> dict:
        """Resolve template variables from the domain.

        Combines payload data with database lookups for names,
        references, and other human-readable values.
        """
        from app.domain.business.models import Business, BusinessProfile
        from app.domain.identity.models import User

        variables: dict = {
            "heading": "",  # Set by template wrapper
        }

        # Business name
        biz_result = await self.session.execute(
            select(Business, BusinessProfile)
            .outerjoin(
                BusinessProfile,
                BusinessProfile.business_id == Business.id,
            )
            .where(Business.id == business_id)
        )
        biz_row = biz_result.one_or_none()
        if biz_row:
            business, profile = biz_row
            variables["business_name"] = profile.display_name if profile else business.name
        else:
            variables["business_name"] = "the business"

        # Customer name
        customer_id = _parse_uuid(payload.get("customer_id"))
        if customer_id:
            user_result = await self.session.execute(select(User).where(User.id == customer_id))
            user = user_result.scalar_one_or_none()
            if user:
                variables["customer_name"] = user.email.split("@")[0]
            else:
                variables["customer_name"] = "there"
        else:
            variables["customer_name"] = "there"

        # Pass through payload values directly
        passthrough_keys = [
            "reference",
            "quote_reference",
            "subject",
            "amount",
            "currency",
            "error",
        ]
        for key in passthrough_keys:
            value = payload.get(key)
            if value is not None:
                variables[key] = str(value)

        # Format amount for display (strip Decimal trailing zeros)
        if "amount" in variables:
            try:
                variables["amount"] = f"{float(variables['amount']):.2f}"
            except (ValueError, TypeError):
                pass

        return variables

    async def _resolve_customer_email(self, customer_id: uuid.UUID) -> str | None:
        """Look up the customer's email address."""
        from app.domain.identity.models import User

        result = await self.session.execute(select(User.email).where(User.id == customer_id))
        return result.scalar_one_or_none()

    async def _resolve_business_emails(self, business_id: uuid.UUID) -> list[str]:
        """Look up email addresses for business members.

        Returns emails of ACTIVE business members with OWNER or ADMIN roles.
        """
        from app.domain.business.models import BusinessMember

        result = await self.session.execute(
            select(BusinessMember).where(
                BusinessMember.business_id == business_id,
                BusinessMember.status == "ACTIVE",
                BusinessMember.role.in_(["OWNER", "ADMIN"]),
                BusinessMember.deleted_at.is_(None),
            )
        )
        members = list(result.scalars().all())

        if not members:
            return []

        from app.domain.identity.models import User

        user_ids = [m.user_id for m in members if m.user_id]
        if not user_ids:
            return []

        email_result = await self.session.execute(select(User.email).where(User.id.in_(user_ids)))
        return [row[0] for row in email_result.all() if row[0]]


# ── Helpers ──────────────────────────────────────────────────────────────


def _render(template: str, variables: dict) -> str:
    """Render a template string with {{ variable }} substitution."""

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = variables.get(var_name)
        if value is not None:
            return str(value)
        return match.group(0)

    return _TEMPLATE_VAR_RE.sub(replacer, template)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    """Safely parse a UUID string."""
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None
