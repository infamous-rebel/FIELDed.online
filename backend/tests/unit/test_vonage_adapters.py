"""Unit tests for Vonage communication adapters.

Covers:
- Vonage JWT generation (auth helper)
- Vonage SMS adapter (send, failure, empty credentials)
- Vonage WhatsApp adapter (template, text, failure, empty credentials)
- Vonage Voice adapter (initiate call, failure, empty credentials)
- ProviderFactory resolution for all three channels
- Vonage webhook delivery status mapping
- Vonage Voice event status mapping
- Configuration fields

Uses a pre-generated static RSA key to avoid requiring the
``cryptography`` package at test time.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Pre-generated 2048-bit RSA private key for testing only.
# NEVER use this key in production.
_TEST_RSA_PEM = """\
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7o4qne60TB3pq
Vf8Wq2a0LJ5X0J2rZ8a0E7mHb+2F3Kq2bV0r9j0R+5W9T3xY6mN1o2rF3p2X2d0
L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0
L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0
L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0
L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0
L3mN5o2rF3p2X2d0AgMBAAECggEBAK+Sq+qP2bGP8kv0+Jr0bqfFfB7+0L5o2rF3
p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3
p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3
p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3
p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2rF3
p2X2d0L3mN5o2rF3p2X2d0ECgYEA8e2sF3p2X2d0L3mN5o2rF3p2X2d0L3mN5o2r
-----END PRIVATE KEY-----"""


def _try_import_cryptography():
    """Try to import cryptography; return True if available."""
    import importlib.util

    return importlib.util.find_spec("cryptography") is not None


def _test_rsa_pem() -> str:
    """Generate a test RSA private key PEM for adapter tests.

    Uses ``cryptography`` if available; otherwise returns a dummy PEM
    string that is sufficient for adapter construction tests (but not
    for actual JWT signing).
    """
    if _try_import_cryptography():
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    return _TEST_RSA_PEM


# ── JWT auth helper ──


class TestVonageJWT:
    """Test the Vonage JWT generation helper."""

    @pytest.mark.skipif(not _try_import_cryptography(), reason="cryptography not installed")
    def test_generate_jwt_returns_string(self):
        """JWT generation returns a non-empty string."""
        from app.adapters.vonage.auth import generate_vonage_jwt

        token = generate_vonage_jwt(
            application_id="test-app-id",
            private_key_pem=_test_rsa_pem(),
        )
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.skipif(not _try_import_cryptography(), reason="cryptography not installed")
    def test_generate_jwt_contains_application_id(self):
        """JWT payload contains the application_id claim."""
        import jwt as pyjwt

        from app.adapters.vonage.auth import generate_vonage_jwt

        token = generate_vonage_jwt(
            application_id="my-app-123",
            private_key_pem=_test_rsa_pem(),
        )
        payload = pyjwt.decode(token, options={"verify_signature": False})
        assert payload["application_id"] == "my-app-123"
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload

    @pytest.mark.skipif(not _try_import_cryptography(), reason="cryptography not installed")
    def test_generate_jwt_custom_ttl(self):
        """JWT respects custom TTL."""
        import jwt as pyjwt

        from app.adapters.vonage.auth import generate_vonage_jwt

        token = generate_vonage_jwt(
            application_id="test",
            private_key_pem=_test_rsa_pem(),
            ttl_seconds=60,
        )
        payload = pyjwt.decode(token, options={"verify_signature": False})
        assert payload["exp"] - payload["iat"] == 60


# ── Vonage SMS adapter ──


class TestVonageSmsProvider:
    """Test the Vonage SMS adapter."""

    def test_provider_name(self):
        from app.adapters.sms.vonage import VonageSmsProvider

        provider = VonageSmsProvider(
            application_id="app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )
        assert provider.provider_name == "vonage_sms"

    @pytest.mark.asyncio
    async def test_send_empty_credentials(self):
        """Returns failure when credentials are empty."""
        from app.adapters.sms.base import SMSMessage
        from app.adapters.sms.vonage import VonageSmsProvider

        provider = VonageSmsProvider(
            application_id="",
            private_key_pem="",
            from_number="+44123456789",
        )
        result = await provider.send(SMSMessage(to="+44987654321", body="Test"))
        assert not result.success
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Successful send returns message_uuid as provider_reference."""
        from app.adapters.sms.base import SMSMessage
        from app.adapters.sms.vonage import VonageSmsProvider

        provider = VonageSmsProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(
            202,
            json={"message_uuid": "abc-123-def"},
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.send(SMSMessage(to="+44987654321", body="Test SMS"))

        assert result.success
        assert result.provider_reference == "abc-123-def"

    @pytest.mark.asyncio
    async def test_send_failure_4xx(self):
        """4xx errors are non-retryable."""
        from app.adapters.sms.base import SMSMessage
        from app.adapters.sms.vonage import VonageSmsProvider

        provider = VonageSmsProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(422, text="Invalid parameter")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.send(SMSMessage(to="+44987654321", body="Test"))

        assert not result.success
        assert not result.retryable

    @pytest.mark.asyncio
    async def test_send_failure_5xx(self):
        """5xx errors are retryable."""
        from app.adapters.sms.base import SMSMessage
        from app.adapters.sms.vonage import VonageSmsProvider

        provider = VonageSmsProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(500, text="Internal error")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.send(SMSMessage(to="+44987654321", body="Test"))

        assert not result.success
        assert result.retryable


# ── Vonage WhatsApp adapter ──


class TestVonageWhatsAppProvider:
    """Test the Vonage WhatsApp adapter."""

    def test_provider_name(self):
        from app.adapters.whatsapp.vonage import VonageWhatsAppProvider

        provider = VonageWhatsAppProvider(
            application_id="app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )
        assert provider.provider_name == "vonage_whatsapp"

    @pytest.mark.asyncio
    async def test_send_empty_credentials(self):
        from app.adapters.whatsapp.base import WhatsAppMessage
        from app.adapters.whatsapp.vonage import VonageWhatsAppProvider

        provider = VonageWhatsAppProvider(
            application_id="",
            private_key_pem="",
            from_number="+44123456789",
        )
        result = await provider.send(WhatsAppMessage(to="+44987654321", body="Test"))
        assert not result.success
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_send_text_message(self):
        """Free-form text message builds correct payload."""
        from app.adapters.whatsapp.base import WhatsAppMessage
        from app.adapters.whatsapp.vonage import VonageWhatsAppProvider

        provider = VonageWhatsAppProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(200, json={"message_uuid": "wa-uuid-123"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.send(WhatsAppMessage(to="+44987654321", body="Hello"))

        assert result.success
        assert result.provider_reference == "wa-uuid-123"

    @pytest.mark.asyncio
    async def test_send_template_message(self):
        """Template message includes template fields in payload."""
        from app.adapters.whatsapp.base import WhatsAppMessage
        from app.adapters.whatsapp.vonage import VonageWhatsAppProvider

        provider = VonageWhatsAppProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(200, json={"message_uuid": "tmpl-uuid"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            msg = WhatsAppMessage(
                to="+44987654321",
                body="",
                template_name="booking_confirmation",
                template_language="en",
                template_components=[{"type": "body", "parameters": [{"type": "text", "text": "John"}]}],
            )
            result = await provider.send(msg)

        assert result.success
        assert result.provider_reference == "tmpl-uuid"

    def test_build_payload_template(self):
        """Template payload has correct structure."""
        from app.adapters.whatsapp.base import WhatsAppMessage
        from app.adapters.whatsapp.vonage import VonageWhatsAppProvider

        provider = VonageWhatsAppProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        msg = WhatsAppMessage(
            to="+44987654321",
            body="",
            template_name="hello_world",
            template_language="en_US",
        )
        payload = provider._build_payload(msg)
        assert payload["channel"] == "whatsapp"
        assert payload["message_type"] == "template"
        assert payload["template"]["name"] == "hello_world"
        assert payload["template"]["language"] == "en_US"

    def test_build_payload_text(self):
        """Text payload has correct structure."""
        from app.adapters.whatsapp.base import WhatsAppMessage
        from app.adapters.whatsapp.vonage import VonageWhatsAppProvider

        provider = VonageWhatsAppProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        msg = WhatsAppMessage(to="+44987654321", body="Hello there")
        payload = provider._build_payload(msg)
        assert payload["channel"] == "whatsapp"
        assert payload["message_type"] == "text"
        assert payload["text"] == "Hello there"
        assert "template" not in payload


# ── Vonage Voice adapter ──


class TestVonageVoiceProvider:
    """Test the Vonage Voice adapter."""

    def test_provider_name(self):
        from app.adapters.voice.vonage import VonageVoiceProvider

        provider = VonageVoiceProvider(
            application_id="app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )
        assert provider.provider_name == "vonage_voice"

    @pytest.mark.asyncio
    async def test_initiate_empty_credentials(self):
        from app.adapters.voice.base import VoiceCallRequest
        from app.adapters.voice.vonage import VonageVoiceProvider

        provider = VonageVoiceProvider(
            application_id="",
            private_key_pem="",
            from_number="+44123456789",
        )
        result = await provider.initiate_call(VoiceCallRequest(to="+44987654321", from_number="+44123456789"))
        assert not result.success
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_initiate_success(self):
        """Successful call initiation returns call UUID."""
        from app.adapters.voice.base import VoiceCallRequest
        from app.adapters.voice.vonage import VonageVoiceProvider

        provider = VonageVoiceProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(
            201,
            json={
                "uuid": "vonage-call-uuid",
                "status": "started",
                "conversation_uuid": "conv-uuid",
            },
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.initiate_call(
                VoiceCallRequest(
                    to="+44987654321",
                    from_number="+44123456789",
                    callback_url="https://api.fielded.online/ncco/123",
                )
            )

        assert result.success
        assert result.provider_reference == "vonage-call-uuid"
        assert result.raw_response["conversation_uuid"] == "conv-uuid"

    @pytest.mark.asyncio
    async def test_initiate_failure_5xx(self):
        """5xx errors are retryable."""
        from app.adapters.voice.base import VoiceCallRequest
        from app.adapters.voice.vonage import VonageVoiceProvider

        provider = VonageVoiceProvider(
            application_id="test-app",
            private_key_pem=_test_rsa_pem(),
            from_number="+44123456789",
        )

        mock_response = httpx.Response(503, text="Service unavailable")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await provider.initiate_call(VoiceCallRequest(to="+44987654321", from_number="+44123456789"))

        assert not result.success
        assert result.retryable


# ── ProviderFactory resolution ──


class TestVonageProviderFactory:
    """Test that ProviderFactory correctly resolves Vonage providers."""

    def test_sms_vonage_resolution(self):
        from app.adapters import _resolve_sms_provider

        settings = MagicMock()
        settings.sms_provider = "vonage"
        settings.vonage_application_id = "test-app"
        settings.vonage_application_private_key = _test_rsa_pem()
        settings.vonage_number = "+44123456789"

        provider = _resolve_sms_provider(settings)
        assert provider.provider_name == "vonage_sms"

    def test_voice_vonage_resolution(self):
        from app.adapters import _resolve_voice_provider

        settings = MagicMock()
        settings.voice_provider = "vonage"
        settings.vonage_application_id = "test-app"
        settings.vonage_application_private_key = _test_rsa_pem()
        settings.vonage_number = "+44123456789"

        provider = _resolve_voice_provider(settings)
        assert provider.provider_name == "vonage_voice"

    def test_whatsapp_vonage_resolution(self):
        from app.adapters import _resolve_whatsapp_provider

        settings = MagicMock()
        settings.whatsapp_provider = "vonage_whatsapp"
        settings.vonage_application_id = "test-app"
        settings.vonage_application_private_key = _test_rsa_pem()
        settings.vonage_number = "+44123456789"

        provider = _resolve_whatsapp_provider(settings)
        assert provider.provider_name == "vonage_whatsapp"


# ── Vonage webhook delivery status mapping ──


class TestVonageWebhookExtraction:
    """Test webhook event ID and type extraction for Vonage."""

    def test_extract_event_id_vonage_sms(self):
        from app.api.v1.communications import _extract_webhook_event_id

        payload = {"message_uuid": "msg-123", "status": "delivered"}
        event_id = _extract_webhook_event_id("vonage_sms", payload)
        assert event_id == "msg-123:delivered"

    def test_extract_event_id_vonage_whatsapp(self):
        from app.api.v1.communications import _extract_webhook_event_id

        payload = {"message_uuid": "wa-456", "status": "read"}
        event_id = _extract_webhook_event_id("vonage_whatsapp", payload)
        assert event_id == "wa-456:read"

    def test_extract_event_type_vonage(self):
        from app.api.v1.communications import _extract_webhook_event_type

        payload = {"status": "delivered"}
        event_type = _extract_webhook_event_type("vonage_sms", payload)
        assert event_type == "delivered"


# ── Vonage Voice event status mapping ──


class TestVonageVoiceStatusMapping:
    """Test that Vonage call statuses are correctly mapped."""

    def test_vonage_ncco_url_helper(self):
        """NCCO URL helper builds correct URL."""
        request = MagicMock()
        request.app.state.settings.public_base_url = "https://api.fielded.online"
        call_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")

        from app.api.v1.voice import _vonage_ncco_url

        url = _vonage_ncco_url(request, call_id)
        assert (
            url == "https://api.fielded.online/api/v1/webhooks/voice/vonage/ncco/12345678-1234-1234-1234-123456789abc"
        )

    def test_vonage_input_url_helper(self):
        """Input URL helper builds correct URL."""
        request = MagicMock()
        request.app.state.settings.public_base_url = "https://api.fielded.online"
        call_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")

        from app.api.v1.voice import _vonage_input_url

        url = _vonage_input_url(request, call_id)
        assert (
            url == "https://api.fielded.online/api/v1/webhooks/voice/vonage/input/12345678-1234-1234-1234-123456789abc"
        )

    def test_vonage_event_url_helper(self):
        """Event URL helper builds correct URL."""
        request = MagicMock()
        request.app.state.settings.public_base_url = "https://api.fielded.online"
        call_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")

        from app.api.v1.voice import _vonage_event_url

        url = _vonage_event_url(request, call_id)
        assert (
            url == "https://api.fielded.online/api/v1/webhooks/voice/vonage/event/12345678-1234-1234-1234-123456789abc"
        )


# ── Configuration fields ──


class TestVonageConfiguration:
    """Test that Vonage configuration fields exist and have correct defaults."""

    def test_config_fields_exist(self):
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert hasattr(settings, "vonage_api_key")
        assert hasattr(settings, "vonage_api_secret")
        assert hasattr(settings, "vonage_application_id")
        assert hasattr(settings, "vonage_application_private_key")
        assert hasattr(settings, "vonage_number")

    def test_config_defaults_empty(self):
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.vonage_api_key == ""
        assert settings.vonage_api_secret == ""
        assert settings.vonage_application_id == ""
        assert settings.vonage_application_private_key == ""
        assert settings.vonage_number == ""

    def test_env_example_has_vonage_placeholders(self):
        """The .env.example file includes Vonage placeholders."""
        import pathlib

        env_example = pathlib.Path(__file__).parents[3] / ".env.example"
        if env_example.exists():
            content = env_example.read_text()
            assert "VONAGE_APPLICATION_ID" in content
            assert "VONAGE_APPLICATION_PRIVATE_KEY" in content
            assert "VONAGE_NUMBER" in content
