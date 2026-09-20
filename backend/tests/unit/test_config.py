"""Unit tests for application configuration."""

from __future__ import annotations

import os

import pytest

from app.config import Environment, Settings


class TestSettings:
    """Test configuration loading and validation."""

    def test_default_settings(self):
        """Settings load with sensible defaults."""
        os.environ["APP_ENV"] = "development"
        settings = Settings()
        assert settings.app_env == Environment.DEVELOPMENT
        assert settings.app_name == "FIELDed"
        assert settings.jwt_algorithm == "HS256"

    def test_production_requires_secret_key(self):
        """Production environment rejects default secret key."""
        os.environ["APP_ENV"] = "production"
        os.environ["APP_SECRET_KEY"] = "change-me-to-a-random-secret"
        with pytest.raises(Exception):
            Settings()
        # Reset
        os.environ["APP_ENV"] = "development"
        os.environ.pop("APP_SECRET_KEY", None)

    def test_cors_origin_list_parsing(self):
        """CORS origins are parsed from comma-separated string."""
        os.environ["BACKEND_CORS_ORIGINS"] = "http://localhost:3000,https://fielded.app"
        settings = Settings()
        assert "http://localhost:3000" in settings.cors_origin_list
        assert "https://fielded.app" in settings.cors_origin_list
        os.environ.pop("BACKEND_CORS_ORIGINS", None)

    def test_is_production_property(self):
        """is_production reflects environment."""
        os.environ["APP_ENV"] = "production"
        os.environ["APP_SECRET_KEY"] = "secure-key-123"
        os.environ["JWT_SECRET_KEY"] = "secure-jwt-key-123"
        settings = Settings()
        assert settings.is_production is True
        # Reset
        os.environ["APP_ENV"] = "development"
        os.environ.pop("APP_SECRET_KEY", None)
        os.environ.pop("JWT_SECRET_KEY", None)

    def test_is_development_property(self):
        """is_development reflects environment."""
        os.environ["APP_ENV"] = "development"
        settings = Settings()
        assert settings.is_development is True

    def test_adapter_defaults_are_mock(self):
        """All adapter providers default to mock/local."""
        os.environ["APP_ENV"] = "development"
        settings = Settings()
        assert settings.ai_provider == "mock"
        assert settings.email_provider == "mock"
        assert settings.storage_provider == "local"
        assert settings.sms_provider == "mock"
        assert settings.calendar_provider == "mock"
