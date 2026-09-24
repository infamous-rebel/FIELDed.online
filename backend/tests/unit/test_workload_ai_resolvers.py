"""Unit tests for per-workload AI provider resolvers.

Tests:
- Workload-specific API key/base URL is used when present.
- Global AI config is used when workload-specific config is empty.
- StubAIProvider is returned when ai_provider == "mock".
- Each workload resolver is independent (discovery, call agent, brain).
- The original _resolve_ai_provider() still works (backward compat).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.adapters import (
    _resolve_ai_provider,
    _resolve_brain_ai_provider,
    _resolve_call_agent_ai_provider,
    _resolve_discovery_ai_provider,
)
from app.adapters.ai.openai_provider import OpenAIProvider
from app.adapters.ai.stub import StubAIProvider


def _make_settings(**overrides: str) -> MagicMock:
    """Build a mock settings object with sensible defaults."""
    settings = MagicMock()
    # Global AI defaults
    settings.ai_provider = "mock"
    settings.ai_api_key = ""
    settings.ai_model = ""
    settings.ai_base_url = ""
    # Per-workload defaults (all empty → fall back to global)
    settings.discovery_ai_api_key = ""
    settings.discovery_ai_base_url = ""
    settings.call_agent_ai_api_key = ""
    settings.call_agent_ai_base_url = ""
    settings.brain_ai_api_key = ""
    settings.brain_ai_base_url = ""
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings


# ---------------------------------------------------------------------------
# Stub fallback when no real provider is configured
# ---------------------------------------------------------------------------


class TestStubFallback:
    """All resolvers return StubAIProvider when ai_provider='mock'."""

    def test_global_resolver_returns_stub(self):
        settings = _make_settings()
        assert isinstance(_resolve_ai_provider(settings), StubAIProvider)

    def test_discovery_resolver_returns_stub(self):
        settings = _make_settings()
        assert isinstance(_resolve_discovery_ai_provider(settings), StubAIProvider)

    def test_call_agent_resolver_returns_stub(self):
        settings = _make_settings()
        assert isinstance(_resolve_call_agent_ai_provider(settings), StubAIProvider)

    def test_brain_resolver_returns_stub(self):
        settings = _make_settings()
        assert isinstance(_resolve_brain_ai_provider(settings), StubAIProvider)

    def test_workload_keys_ignored_when_provider_is_mock(self):
        """Even with workload keys set, mock provider → StubAIProvider."""
        settings = _make_settings(
            ai_provider="mock",
            discovery_ai_api_key="gsk_discovery_key",
            call_agent_ai_api_key="gsk_call_key",
            brain_ai_api_key="gsk_brain_key",
        )
        assert isinstance(_resolve_discovery_ai_provider(settings), StubAIProvider)
        assert isinstance(_resolve_call_agent_ai_provider(settings), StubAIProvider)
        assert isinstance(_resolve_brain_ai_provider(settings), StubAIProvider)


# ---------------------------------------------------------------------------
# Global config used when workload-specific config is empty
# ---------------------------------------------------------------------------


class TestGlobalFallback:
    """When workload-specific key/base_url are empty, global values are used."""

    def test_discovery_uses_global_key(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
            # discovery-specific: empty
        )
        provider = _resolve_discovery_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)

    def test_call_agent_uses_global_key(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
        )
        provider = _resolve_call_agent_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)

    def test_brain_uses_global_key(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
        )
        provider = _resolve_brain_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)


# ---------------------------------------------------------------------------
# Workload-specific config overrides global
# ---------------------------------------------------------------------------


class TestWorkloadOverride:
    """When workload-specific key is set, it takes precedence over global."""

    def test_discovery_uses_workload_key_over_global(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
            discovery_ai_api_key="gsk_discovery_specific",
            discovery_ai_base_url="https://api.groq.com/openai/v1",
        )
        provider = _resolve_discovery_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)
        # Verify the workload-specific key is used (not the global one)
        assert provider._api_key == "gsk_discovery_specific"

    def test_call_agent_uses_workload_key_over_global(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
            call_agent_ai_api_key="gsk_call_specific",
            call_agent_ai_base_url="https://api.groq.com/openai/v1",
        )
        provider = _resolve_call_agent_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)
        assert provider._api_key == "gsk_call_specific"

    def test_brain_uses_workload_key_over_global(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
            brain_ai_api_key="gsk_brain_specific",
            brain_ai_base_url="https://api.groq.com/openai/v1",
        )
        provider = _resolve_brain_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)
        assert provider._api_key == "gsk_brain_specific"

    def test_workload_base_url_overrides_global(self):
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_key",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
            discovery_ai_api_key="gsk_key",
            discovery_ai_base_url="https://custom-endpoint.example.com/v1",
        )
        provider = _resolve_discovery_ai_provider(settings)
        assert isinstance(provider, OpenAIProvider)
        assert provider._api_base == "https://custom-endpoint.example.com/v1"

    def test_three_workloads_independent_keys(self):
        """Each workload can have its own key simultaneously."""
        settings = _make_settings(
            ai_provider="openai",
            ai_api_key="gsk_global",
            ai_base_url="https://api.groq.com/openai/v1",
            ai_model="llama-3.1",
            discovery_ai_api_key="gsk_discovery",
            call_agent_ai_api_key="gsk_call",
            brain_ai_api_key="gsk_brain",
        )
        discovery = _resolve_discovery_ai_provider(settings)
        call_agent = _resolve_call_agent_ai_provider(settings)
        brain = _resolve_brain_ai_provider(settings)

        assert isinstance(discovery, OpenAIProvider)
        assert isinstance(call_agent, OpenAIProvider)
        assert isinstance(brain, OpenAIProvider)

        assert discovery._api_key == "gsk_discovery"
        assert call_agent._api_key == "gsk_call"
        assert brain._api_key == "gsk_brain"


# ---------------------------------------------------------------------------
# Config field presence
# ---------------------------------------------------------------------------


class TestConfigFields:
    """Verify config.py has all per-workload fields."""

    def test_settings_has_workload_fields(self):
        from app.config import Settings

        settings = Settings()
        assert hasattr(settings, "discovery_ai_api_key")
        assert hasattr(settings, "discovery_ai_base_url")
        assert hasattr(settings, "call_agent_ai_api_key")
        assert hasattr(settings, "call_agent_ai_base_url")
        assert hasattr(settings, "brain_ai_api_key")
        assert hasattr(settings, "brain_ai_base_url")

    def test_workload_fields_default_empty(self):
        from app.config import Settings

        settings = Settings()
        assert settings.discovery_ai_api_key == ""
        assert settings.discovery_ai_base_url == ""
        assert settings.call_agent_ai_api_key == ""
        assert settings.call_agent_ai_base_url == ""
        assert settings.brain_ai_api_key == ""
        assert settings.brain_ai_base_url == ""


# ---------------------------------------------------------------------------
# Endpoint wiring verification
# ---------------------------------------------------------------------------


class TestEndpointWiring:
    """Verify that discovery and voice endpoints use their workload resolvers."""

    def test_discovery_endpoint_uses_discovery_resolver(self):
        """discovery._get_ai_provider calls _resolve_discovery_ai_provider."""
        from unittest.mock import patch

        from app.api.v1.discovery import _get_ai_provider

        mock_request = MagicMock()
        mock_settings = MagicMock()
        mock_request.app.state.settings = mock_settings

        sentinel = StubAIProvider()
        with patch(
            "app.api.v1.discovery._resolve_discovery_ai_provider",
            return_value=sentinel,
        ) as mock_resolve:
            result = _get_ai_provider(mock_request)

        mock_resolve.assert_called_once_with(mock_settings)
        assert result is sentinel
