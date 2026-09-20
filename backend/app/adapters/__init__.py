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

from app.adapters.ai.base import AIProvider
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
        )


def _resolve_email_provider(settings: object) -> EmailProvider:
    """Resolve the configured email provider."""
    provider_name = getattr(settings, "email_provider", "mock")

    if provider_name == "resend":
        from app.adapters.email.resend import ResendEmailProvider

        api_key = getattr(settings, "email_api_key", "")
        from_address = getattr(settings, "email_from", "noreply@fielded.local")
        if not api_key:
            logger.warning(
                "Resend email provider selected but EMAIL_API_KEY is empty. "
                "Email sending will fail."
            )
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
    provider_name = getattr(settings, "ai_provider", "mock")

    if provider_name == "openai":
        from app.adapters.ai.openai_provider import OpenAIProvider

        api_key = getattr(settings, "ai_api_key", "")
        model = getattr(settings, "ai_model", "") or "gpt-4o-mini"
        if not api_key:
            logger.warning(
                "OpenAI AI provider selected but AI_API_KEY is empty. "
                "AI calls will fail."
            )
        return OpenAIProvider(api_key=api_key, model=model)

    if provider_name not in ("mock", "stub"):
        logger.warning(
            "AI provider '%s' not implemented as real adapter. Using the deterministic stub.",
            provider_name,
        )
    from app.adapters.ai.stub import StubAIProvider

    return StubAIProvider()


def _resolve_whatsapp_provider(settings: object) -> WhatsAppProvider:
    """Resolve the configured WhatsApp provider."""
    from app.adapters.whatsapp.stub import StubWhatsAppProvider

    return StubWhatsAppProvider()


def _resolve_push_provider(settings: object) -> PushProvider:
    """Resolve the configured push provider."""
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
                "Stripe payment provider selected but PAYMENT_API_KEY is empty. "
                "Payment operations will fail."
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
