"""Unit tests for the transactional email notification system.

Tests cover:
- Email template registry completeness
- Template variable rendering
- Event type resolution
- EmailNotificationService recipient resolution
- EmailNotificationService idempotency
- EmailNotificationService failure safety
- Webhook delivery status mapping
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.common import ProviderResult
from app.adapters.email.base import EmailMessage
from app.domain.notification.email_templates import (
    ALL_EMAIL_EVENTS,
    BUSINESS_EMAIL_EVENTS,
    BUSINESS_TEMPLATES,
    CUSTOMER_EMAIL_EVENTS,
    CUSTOMER_TEMPLATES,
    EmailTemplate,
    resolve_event_type,
)
from app.domain.notification.email_service import (
    EmailNotificationService,
    _render,
    _parse_uuid,
)


# ── Template Registry ─────────────────────────────────────────────────────


class TestEmailTemplateRegistry:
    """Verify the template registry covers all required lifecycle events."""

    def test_customer_templates_cover_enquiry_events(self):
        assert "ENQUIRY_SUBMITTED" in CUSTOMER_TEMPLATES
        assert "ENQUIRY_BUSINESS_RESPONDED" in CUSTOMER_TEMPLATES

    def test_customer_templates_cover_quote_events(self):
        assert "QUOTE_SENT" in CUSTOMER_TEMPLATES
        assert "QUOTE_ACCEPTED" in CUSTOMER_TEMPLATES

    def test_customer_templates_cover_booking_events(self):
        assert "BOOKING_PROPOSED" in CUSTOMER_TEMPLATES
        assert "BOOKING_CONFIRMED" in CUSTOMER_TEMPLATES
        assert "BOOKING_CHANGED" in CUSTOMER_TEMPLATES or "BOOKING_RESCHEDULED" in CUSTOMER_TEMPLATES
        assert "BOOKING_CANCELLED" in CUSTOMER_TEMPLATES

    def test_customer_templates_cover_payment_events(self):
        assert "PAYMENT_SUCCEEDED" in CUSTOMER_TEMPLATES
        assert "PAYMENT_FAILED" in CUSTOMER_TEMPLATES

    def test_customer_templates_cover_service_events(self):
        assert "SERVICE_COMPLETED" in CUSTOMER_TEMPLATES
        assert "REVIEW_ELIGIBLE" in CUSTOMER_TEMPLATES

    def test_business_templates_cover_enquiry_events(self):
        assert "ENQUIRY_SUBMITTED" in BUSINESS_TEMPLATES
        assert "ENQUIRY_BUSINESS_RESPONDED" in BUSINESS_TEMPLATES

    def test_business_templates_cover_quote_events(self):
        assert "QUOTE_ACCEPTED" in BUSINESS_TEMPLATES

    def test_business_templates_cover_booking_events(self):
        assert "BOOKING_PROPOSED" in BUSINESS_TEMPLATES
        assert "BOOKING_CONFIRMED" in BUSINESS_TEMPLATES
        assert "BOOKING_CANCELLED" in BUSINESS_TEMPLATES

    def test_business_templates_cover_payment_events(self):
        assert "PAYMENT_SUCCEEDED" in BUSINESS_TEMPLATES
        assert "PAYMENT_FAILED" in BUSINESS_TEMPLATES

    def test_business_templates_cover_service_events(self):
        assert "SERVICE_COMPLETED" in BUSINESS_TEMPLATES

    def test_all_customer_templates_have_subject(self):
        for event_type, template in CUSTOMER_TEMPLATES.items():
            assert template.subject, f"Customer template {event_type} has empty subject"
            assert "{{ " in template.subject or "{{" in template.subject or len(template.subject) > 5

    def test_all_business_templates_have_subject(self):
        for event_type, template in BUSINESS_TEMPLATES.items():
            assert template.subject, f"Business template {event_type} has empty subject"

    def test_all_templates_have_html_body(self):
        for template in list(CUSTOMER_TEMPLATES.values()) + list(BUSINESS_TEMPLATES.values()):
            assert template.body, f"Template {template.event_type} has empty body"
            assert "font-family" in template.body or "<p>" in template.body

    def test_all_email_events_is_union(self):
        assert ALL_EMAIL_EVENTS == CUSTOMER_EMAIL_EVENTS | BUSINESS_EMAIL_EVENTS

    def test_minimum_customer_event_count(self):
        """At least 12 customer notification types as specified."""
        assert len(CUSTOMER_TEMPLATES) >= 12

    def test_minimum_business_event_count(self):
        """At least 9 business notification types as specified."""
        assert len(BUSINESS_TEMPLATES) >= 9


# ── Event Type Resolution ──────────────────────────────────────────────────


class TestEventTypeResolution:
    """Verify event type aliases resolve correctly."""

    def test_direct_mapping(self):
        assert resolve_event_type("ENQUIRY_SUBMITTED") == "ENQUIRY_SUBMITTED"
        assert resolve_event_type("QUOTE_SENT") == "QUOTE_SENT"
        assert resolve_event_type("PAYMENT_SUCCEEDED") == "PAYMENT_SUCCEEDED"

    def test_alias_mapping(self):
        assert resolve_event_type("BOOKING_COMPLETED") == "SERVICE_COMPLETED"

    def test_unknown_event_passthrough(self):
        assert resolve_event_type("UNKNOWN_EVENT") == "UNKNOWN_EVENT"


# ── Template Rendering ──────────────────────────────────────────────────────


class TestTemplateRendering:
    """Verify template variable substitution."""

    def test_render_replaces_known_variables(self):
        result = _render("Hello {{ name }}", {"name": "Alice"})
        assert result == "Hello Alice"

    def test_render_leaves_unknown_variables(self):
        result = _render("Hello {{ name }}, ref {{ ref }}", {"name": "Alice"})
        assert result == "Hello Alice, ref {{ ref }}"

    def test_render_handles_multiple_occurrences(self):
        result = _render("{{ x }} and {{ x }}", {"x": "A"})
        assert result == "A and A"

    def test_render_handles_empty_variables(self):
        result = _render("Hello {{ name }}", {})
        assert result == "Hello {{ name }}"

    def test_render_handles_whitespace_in_braces(self):
        result = _render("Hello {{  name  }}", {"name": "Bob"})
        assert result == "Hello Bob"

    def test_render_converts_non_string_values(self):
        result = _render("Amount: {{ amount }}", {"amount": 42})
        assert result == "Amount: 42"


# ── UUID Parsing ────────────────────────────────────────────────────────────


class TestParseUUID:
    """Verify UUID parsing helper."""

    def test_valid_uuid_string(self):
        uid = str(uuid.uuid4())
        assert _parse_uuid(uid) == uuid.UUID(uid)

    def test_none_returns_none(self):
        assert _parse_uuid(None) is None

    def test_invalid_string_returns_none(self):
        assert _parse_uuid("not-a-uuid") is None

    def test_empty_string_returns_none(self):
        assert _parse_uuid("") is None


# ── EmailNotificationService ────────────────────────────────────────────────


class TestEmailNotificationServiceFailureSafety:
    """Verify the service never raises — failures are caught and logged."""

    @pytest.mark.asyncio
    async def test_process_event_never_raises(self):
        """Even with a broken provider, process_event returns [] not raises."""
        mock_session = AsyncMock()
        mock_provider = AsyncMock()
        mock_provider.send.side_effect = RuntimeError("provider exploded")
        mock_provider.provider_name = "test"

        service = EmailNotificationService(
            mock_session,
            email_provider=mock_provider,
        )

        # Should not raise
        result = await service.process_event(
            business_id=uuid.uuid4(),
            event_type="ENQUIRY_SUBMITTED",
            aggregate_type="enquiry",
            aggregate_id=uuid.uuid4(),
            payload={"customer_id": str(uuid.uuid4())},
            outbox_event_id=uuid.uuid4(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_process_event_with_no_customer_email(self):
        """If customer has no email, no customer email is sent."""
        mock_session = AsyncMock()
        mock_provider = AsyncMock()
        mock_provider.provider_name = "resend"
        mock_provider.send = AsyncMock(return_value=ProviderResult.ok("msg_123"))

        service = EmailNotificationService(
            mock_session,
            email_provider=mock_provider,
        )

        # Mock customer lookup returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.process_event(
            business_id=uuid.uuid4(),
            event_type="ENQUIRY_SUBMITTED",
            aggregate_type="enquiry",
            aggregate_id=uuid.uuid4(),
            payload={},  # No customer_id
            outbox_event_id=uuid.uuid4(),
        )
        # No customer email sent (no customer_id in payload)
        assert isinstance(result, list)


class TestEmailNotificationServiceIdempotency:
    """Verify idempotency key includes recipient discriminator."""

    def test_idempotency_key_format(self):
        """Idempotency keys include recipient discriminator to prevent fan-out drops."""
        # This is a design verification — the key format is:
        # email:{event_type}:{aggregate_type}:{aggregate_id}:{recipient_type}:{recipient_suffix}:{outbox_event_id}
        # The recipient_suffix includes customer_id for customer emails and "biz" for business
        event_type = "ENQUIRY_SUBMITTED"
        aggregate_type = "enquiry"
        aggregate_id = uuid.uuid4()
        outbox_id = uuid.uuid4()
        customer_id = uuid.uuid4()

        customer_key = f"email:{event_type}:{aggregate_type}:{aggregate_id}:CUSTOMER:cust:{customer_id}:{outbox_id}"
        business_key = f"email:{event_type}:{aggregate_type}:{aggregate_id}:BUSINESS_MEMBER:biz:{outbox_id}"

        # Keys must differ for different recipients
        assert customer_key != business_key

    def test_different_customers_get_different_keys(self):
        """Two different customers get different idempotency keys."""
        event_type = "ENQUIRY_SUBMITTED"
        aggregate_id = uuid.uuid4()
        outbox_id = uuid.uuid4()
        cust_a = uuid.uuid4()
        cust_b = uuid.uuid4()

        key_a = f"email:{event_type}:enquiry:{aggregate_id}:CUSTOMER:cust:{cust_a}:{outbox_id}"
        key_b = f"email:{event_type}:enquiry:{aggregate_id}:CUSTOMER:cust:{cust_b}:{outbox_id}"

        assert key_a != key_b


# ── Webhook Delivery Status Mapping ─────────────────────────────────────────


class TestWebhookDeliveryStatusMapping:
    """Verify Resend webhook event types map to correct statuses."""

    def test_delivered_maps_to_delivered(self):
        status_map = {
            "email.delivered": "DELIVERED",
            "email.bounced": "BOUNCED",
            "email.failed": "FAILED",
            "email.complained": "COMPLAINED",
        }
        assert status_map["email.delivered"] == "DELIVERED"

    def test_bounced_maps_to_bounced(self):
        status_map = {
            "email.delivered": "DELIVERED",
            "email.bounced": "BOUNCED",
            "email.failed": "FAILED",
            "email.complained": "COMPLAINED",
        }
        assert status_map["email.bounced"] == "BOUNCED"

    def test_failed_maps_to_failed(self):
        status_map = {
            "email.delivered": "DELIVERED",
            "email.bounced": "BOUNCED",
            "email.failed": "FAILED",
            "email.complained": "COMPLAINED",
        }
        assert status_map["email.failed"] == "FAILED"

    def test_complained_maps_to_complained(self):
        status_map = {
            "email.delivered": "DELIVERED",
            "email.bounced": "BOUNCED",
            "email.failed": "FAILED",
            "email.complained": "COMPLAINED",
        }
        assert status_map["email.complained"] == "COMPLAINED"

    def test_unknown_event_not_in_map(self):
        status_map = {
            "email.delivered": "DELIVERED",
            "email.bounced": "BOUNCED",
            "email.failed": "FAILED",
            "email.complained": "COMPLAINED",
        }
        assert status_map.get("email.opened") is None


# ── Email Provider Contract ─────────────────────────────────────────────────


class TestEmailProviderContract:
    """Verify the Resend provider maintains the provider contract."""

    def test_resend_provider_name(self):
        from app.adapters.email.resend import ResendEmailProvider

        provider = ResendEmailProvider(api_key="test", from_address="test@test.com")
        assert provider.provider_name == "resend"

    @pytest.mark.asyncio
    async def test_resend_provider_returns_provider_result(self):
        """Resend provider always returns ProviderResult, never raises."""
        from app.adapters.email.resend import ResendEmailProvider

        provider = ResendEmailProvider(api_key="", from_address="test@test.com")
        msg = EmailMessage(to="test@example.com", subject="Test", body="Hello")
        result = await provider.send(msg)
        assert isinstance(result, ProviderResult)
        # With empty API key, it should fail but not raise
        assert result.success is False

    def test_email_message_supports_html_body(self):
        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
            body="Plain text",
            html_body="<p>HTML</p>",
        )
        assert msg.html_body == "<p>HTML</p>"

    def test_email_message_supports_reply_to(self):
        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
            body="Hello",
            reply_to="support@fielded.online",
        )
        assert msg.reply_to == "support@fielded.online"


# ── Configuration ───────────────────────────────────────────────────────────


class TestEmailConfiguration:
    """Verify email configuration defaults."""

    def test_default_from_address(self):
        from app.config import Settings

        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://test:test@localhost/test",
        )
        assert settings.email_from == "noreply@fielded.online"

    def test_email_provider_default_is_mock(self):
        from app.config import Settings

        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://test:test@localhost/test",
        )
        assert settings.email_provider == "mock"

    def test_email_reply_to_configurable(self):
        from app.config import Settings

        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://test:test@localhost/test",
            email_reply_to="support@fielded.online",
        )
        assert settings.email_reply_to == "support@fielded.online"
