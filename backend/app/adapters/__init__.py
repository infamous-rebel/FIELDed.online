"""Adapter interfaces for external services.

All external service integrations use abstract base classes.
Concrete implementations are selected at runtime based on configuration.
This ensures FIELDed core domain logic is provider-independent.

ProviderFactory resolves configured providers from application settings.
Domain services receive provider interfaces through dependency injection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.adapters.accounting.base import AccountingProvider
from app.adapters.ai.base import AIProvider
from app.adapters.calendar.base import CalendarProvider
from app.adapters.crm.base import CRMProvider
from app.adapters.email.base import EmailProvider
from app.adapters.payment.base import PaymentProvider
from app.adapters.push.base import PushProvider
from app.adapters.sms.base import SMSProvider
from app.adapters.voice.base import VoiceProvider
from app.adapters.whatsapp.base import WhatsAppProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderFactory:
    """Resolves configured provider adapters from application settings.

    Domain services receive provider interfaces from this factory.
    No domain/service module imports a concrete SDK directly.
    """

    email_provider: EmailProvider
    sms_provider: SMSProvider
    voice_provider: VoiceProvider
    whatsapp_provider: WhatsAppProvider
    push_provider: PushProvider
    payment_provider: PaymentProvider
    calendar_provider: CalendarProvider
    accounting_provider: AccountingProvider
    crm_provider: CRMProvider

    @classmethod
    def from_settings(cls, settings: object) -> ProviderFactory:
        """Build providers from application settings.

        Args:
            settings: Application Settings object with provider
                configuration attributes.
        """
        return cls(
            email_provider=_resolve_email_provider(settings),
            sms_provider=_resolve_sms_provider(settings),
            voice_provider=_resolve_voice_provider(settings),
            whatsapp_provider=_resolve_whatsapp_provider(settings),
            push_provider=_resolve_push_provider(settings),
            payment_provider=_resolve_payment_provider(settings),
            calendar_provider=_resolve_calendar_provider(settings),
            accounting_provider=_resolve_accounting_provider(settings),
            crm_provider=_resolve_crm_provider(settings),
        )


def _resolve_email_provider(settings: object) -> EmailProvider:
    """Resolve the configured email provider."""
    provider_name = getattr(settings, "email_provider", "mock")

    if provider_name == "resend":
        from app.adapters.email.resend import ResendEmailProvider

        api_key = getattr(settings, "email_api_key", "")
        from_address = getattr(settings, "email_from", "noreply@fielded.local")
        if not api_key:
            logger.warning("Resend email provider selected but EMAIL_API_KEY is empty. Email sending will fail.")
        return ResendEmailProvider(api_key=api_key, from_address=from_address)

    # Default: mock/stub — log and return a no-op
    from app.adapters.email.resend import ResendEmailProvider

    logger.info(
        "Email provider '%s' not implemented as real adapter. "
        "Using Resend provider with empty key (will fail on send).",
        provider_name,
    )
    return ResendEmailProvider(api_key="", from_address="noreply@fielded.local")


def _resolve_sms_provider(settings: object) -> SMSProvider:
    """Resolve the configured SMS provider."""
    provider_name = getattr(settings, "sms_provider", "mock")

    if provider_name == "twilio":
        from app.adapters.sms.twilio import TwilioSmsProvider

        account_sid = getattr(settings, "twilio_account_sid", "")
        auth_token = getattr(settings, "twilio_auth_token", "")
        from_number = getattr(settings, "twilio_phone_number", "")
        if not account_sid or not auth_token:
            logger.warning("Twilio SMS provider selected but Twilio credentials are empty.")
        return TwilioSmsProvider(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
        )

    logger.info("SMS provider '%s' — using Twilio with empty config.", provider_name)
    from app.adapters.sms.twilio import TwilioSmsProvider

    return TwilioSmsProvider(account_sid="", auth_token="", from_number="")


def _resolve_voice_provider(settings: object) -> VoiceProvider:
    """Resolve the configured voice provider."""
    provider_name = getattr(settings, "voice_provider", "mock")

    if provider_name == "twilio":
        from app.adapters.voice.twilio import TwilioVoiceProvider

        account_sid = getattr(settings, "twilio_account_sid", "")
        auth_token = getattr(settings, "twilio_auth_token", "")
        from_number = getattr(settings, "twilio_phone_number", "")
        return TwilioVoiceProvider(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
        )

    logger.info("Voice provider '%s' — using Twilio with empty config.", provider_name)
    from app.adapters.voice.twilio import TwilioVoiceProvider

    return TwilioVoiceProvider(account_sid="", auth_token="", from_number="")


def _resolve_ai_provider(settings: object) -> AIProvider:
    """Resolve the configured AI/LLM provider.

    Phase 14C:  supports ``openai`` as a real conversational provider
    (required for voice Call Agent conversations).  The deterministic
    stub remains available for discovery and testing.
    """
    return _build_ai_provider(settings)


def _build_ai_provider(
    settings: object,
    *,
    api_key_override: str = "",
    base_url_override: str = "",
) -> AIProvider:
    """Shared builder: construct an AI provider from settings with optional overrides.

    Workload-specific resolvers pass their dedicated key/base_url as
    overrides.  When the override is empty the global ``ai_api_key`` /
    ``ai_base_url`` are used instead.
    """
    provider_name = getattr(settings, "ai_provider", "mock")

    if provider_name == "openai":
        from app.adapters.ai.openai_provider import OpenAIProvider

        api_key = api_key_override or getattr(settings, "ai_api_key", "")
        model = getattr(settings, "ai_model", "") or "gpt-4o-mini"
        base_url = base_url_override or getattr(settings, "ai_base_url", "") or None
        if not api_key:
            logger.warning("OpenAI AI provider selected but AI_API_KEY is empty. AI calls will fail.")
        kwargs: dict[str, Any] = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["api_base"] = base_url
        return OpenAIProvider(**kwargs)

    if provider_name == "groq":
        from app.adapters.ai.groq import GroqProvider

        api_key = api_key_override or getattr(settings, "ai_api_key", "")
        model = getattr(settings, "ai_model", "") or "llama-3.3-70b-versatile"
        base_url = base_url_override or getattr(settings, "ai_base_url", "") or None
        if not api_key:
            logger.warning("Groq AI provider selected but AI_API_KEY is empty. AI calls will fail.")
        kwargs: dict[str, Any] = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["api_base"] = base_url
        return GroqProvider(**kwargs)

    if provider_name not in ("mock", "stub"):
        logger.warning(
            "AI provider '%s' not implemented as real adapter. Using the deterministic stub.",
            provider_name,
        )
    from app.adapters.ai.stub import StubAIProvider

    return StubAIProvider()


# ---------------------------------------------------------------------------
# Per-workload AI provider resolvers
# ---------------------------------------------------------------------------


def _resolve_discovery_ai_provider(settings: object) -> AIProvider:
    """Resolve AI provider for the Discovery workload.

    Uses ``DISCOVERY_AI_API_KEY`` / ``DISCOVERY_AI_BASE_URL`` when set,
    otherwise falls back to the global ``AI_API_KEY`` / ``AI_BASE_URL``.
    """
    return _build_ai_provider(
        settings,
        api_key_override=getattr(settings, "discovery_ai_api_key", ""),
        base_url_override=getattr(settings, "discovery_ai_base_url", ""),
    )


def _resolve_call_agent_ai_provider(settings: object) -> AIProvider:
    """Resolve AI provider for the Call Agent (voice) workload.

    Uses ``CALL_AGENT_AI_API_KEY`` / ``CALL_AGENT_AI_BASE_URL`` when set,
    otherwise falls back to the global ``AI_API_KEY`` / ``AI_BASE_URL``.
    """
    return _build_ai_provider(
        settings,
        api_key_override=getattr(settings, "call_agent_ai_api_key", ""),
        base_url_override=getattr(settings, "call_agent_ai_base_url", ""),
    )


def _resolve_brain_ai_provider(settings: object) -> AIProvider:
    """Resolve AI provider for the Business Brain workload.

    Uses ``BRAIN_AI_API_KEY`` / ``BRAIN_AI_BASE_URL`` when set,
    otherwise falls back to the global ``AI_API_KEY`` / ``AI_BASE_URL``.

    Note: the Business Brain evaluator is currently entirely deterministic
    and does not call AI.  This resolver is available for future Brain
    workloads that need AI (e.g. rule drafting, intent classification).
    """
    return _build_ai_provider(
        settings,
        api_key_override=getattr(settings, "brain_ai_api_key", ""),
        base_url_override=getattr(settings, "brain_ai_base_url", ""),
    )


def _resolve_whatsapp_provider(settings: object) -> WhatsAppProvider:
    """Resolve the configured WhatsApp provider."""
    provider_name = getattr(settings, "whatsapp_provider", "mock")

    if provider_name == "whatsapp_cloud":
        from app.adapters.whatsapp.cloud import WhatsAppCloudProvider

        access_token = getattr(settings, "whatsapp_api_key", "")
        phone_number_id = getattr(settings, "whatsapp_phone_number_id", "")
        if not access_token:
            logger.warning("WhatsApp Cloud provider selected but WHATSAPP_API_KEY is empty.")
        return WhatsAppCloudProvider(access_token=access_token, phone_number_id=phone_number_id)

    if provider_name not in ("mock", "stub"):
        logger.warning("WhatsApp provider '%s' not recognised. Using stub.", provider_name)

    from app.adapters.whatsapp.stub import StubWhatsAppProvider

    return StubWhatsAppProvider()


def _resolve_push_provider(settings: object) -> PushProvider:
    """Resolve the configured push provider."""
    provider_name = getattr(settings, "push_provider", "mock")

    if provider_name == "firebase":
        from app.adapters.push.firebase import FirebasePushProvider

        server_key = getattr(settings, "push_api_key", "")
        project_id = getattr(settings, "firebase_project_id", "")
        if not server_key:
            logger.warning("Firebase push provider selected but PUSH_API_KEY is empty.")
        return FirebasePushProvider(project_id=project_id, server_key=server_key)

    if provider_name not in ("mock", "stub"):
        logger.warning("Push provider '%s' not recognised. Using stub.", provider_name)

    from app.adapters.push.stub import StubPushProvider

    return StubPushProvider()


def _resolve_payment_provider(settings: object) -> PaymentProvider:
    """Resolve the configured payment provider.

    FIELDed selects Stripe as the default payment provider.
    The stub provider is used for development/testing when
    PAYMENT_PROVIDER=mock or PAYMENT_PROVIDER=stub.
    """
    provider_name = getattr(settings, "payment_provider", "mock")

    if provider_name == "stripe":
        from app.adapters.payment.stripe_provider import StripePaymentProvider

        api_key = getattr(settings, "payment_api_key", "")
        webhook_secret = getattr(settings, "payment_webhook_secret", "")
        if not api_key:
            logger.warning(
                "Stripe payment provider selected but PAYMENT_API_KEY is empty. Payment operations will fail."
            )
        return StripePaymentProvider(
            api_key=api_key,
            webhook_secret=webhook_secret,
        )

    if provider_name not in ("mock", "stub"):
        logger.warning(
            "Payment provider '%s' not recognised. Using stub provider.",
            provider_name,
        )

    from app.adapters.payment.stub import StubPaymentProvider

    return StubPaymentProvider()


def _resolve_calendar_provider(settings: object) -> CalendarProvider:
    """Resolve the configured calendar provider."""
    provider_name = getattr(settings, "calendar_provider", "mock")

    if provider_name == "google":
        from app.adapters.calendar.google_calendar import GoogleCalendarProvider

        api_key = getattr(settings, "calendar_api_key", "")
        calendar_id = getattr(settings, "google_calendar_id", "primary")
        if not api_key:
            logger.warning("Google Calendar provider selected but CALENDAR_API_KEY is empty.")
        return GoogleCalendarProvider(api_key=api_key, calendar_id=calendar_id)

    if provider_name not in ("mock", "stub"):
        logger.warning("Calendar provider '%s' not recognised. Using stub.", provider_name)

    from app.adapters.calendar.stub import StubCalendarProvider

    return StubCalendarProvider()


def _resolve_accounting_provider(settings: object) -> AccountingProvider:
    """Resolve the configured accounting provider."""
    provider_name = getattr(settings, "accounting_provider", "mock")

    if provider_name == "xero":
        from app.adapters.accounting.xero import XeroAccountingProvider

        api_key = getattr(settings, "accounting_api_key", "")
        tenant_id = getattr(settings, "xero_tenant_id", "")
        if not api_key:
            logger.warning("Xero accounting provider selected but ACCOUNTING_API_KEY is empty.")
        return XeroAccountingProvider(access_token=api_key, tenant_id=tenant_id)

    if provider_name not in ("mock", "stub"):
        logger.warning("Accounting provider '%s' not implemented. Using stub.", provider_name)

    from app.adapters.accounting.stub import StubAccountingProvider

    return StubAccountingProvider()


def _resolve_crm_provider(settings: object) -> CRMProvider:
    """Resolve the configured CRM provider."""
    provider_name = getattr(settings, "crm_provider", "mock")

    if provider_name == "hubspot":
        from app.adapters.crm.hubspot import HubSpotCRMProvider

        api_key = getattr(settings, "crm_api_key", "")
        if not api_key:
            logger.warning("HubSpot CRM provider selected but CRM_API_KEY is empty.")
        return HubSpotCRMProvider(access_token=api_key)

    if provider_name not in ("mock", "stub"):
        logger.warning("CRM provider '%s' not implemented. Using stub.", provider_name)

    from app.adapters.crm.stub import StubCRMProvider

    return StubCRMProvider()
