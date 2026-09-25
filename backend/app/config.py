"""Application configuration via Pydantic Settings.

All configuration is loaded from environment variables.
Environment boundaries: development, staging, production.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """FIELDed application settings.

    All values are loaded from environment variables.
    The .env file in the project root is loaded in development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "FIELDed"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_secret_key: str = "change-me-to-a-random-secret"

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://fielded:fielded@localhost:5432/fielded"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-to-a-random-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Adapter providers (all default to mock/local)
    ai_provider: str = "mock"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = ""  # Optional: override for OpenAI-compatible providers (e.g. Groq)

    # Per-workload AI overrides (empty → fall back to global ai_* fields)
    discovery_ai_api_key: str = ""
    discovery_ai_base_url: str = ""
    call_agent_ai_api_key: str = ""
    call_agent_ai_base_url: str = ""
    brain_ai_api_key: str = ""
    brain_ai_base_url: str = ""

    email_provider: str = "mock"
    email_api_key: str = ""
    email_from: str = "noreply@fielded.local"

    storage_provider: str = "local"
    storage_bucket: str = "fielded-uploads"
    storage_base_path: str = "./uploads"

    sms_provider: str = "mock"
    sms_api_key: str = ""

    calendar_provider: str = "mock"
    calendar_api_key: str = ""

    # Phase 14A — Communication providers
    whatsapp_provider: str = "mock"
    whatsapp_api_key: str = ""
    whatsapp_phone_number_id: str = ""

    push_provider: str = "mock"
    push_api_key: str = ""
    firebase_project_id: str = ""

    voice_provider: str = "mock"

    # Twilio (shared across SMS + Voice)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Phase 14C — Public base URL for Twilio webhooks
    public_base_url: str = ""

    # Phase 15 — Payment provider
    payment_provider: str = "mock"
    payment_api_key: str = ""
    payment_webhook_secret: str = ""

    # Phase 19 — Calendar provider (google_calendar_id added below)
    google_calendar_id: str = "primary"

    # Phase 19 — Accounting provider
    accounting_provider: str = "mock"
    accounting_api_key: str = ""

    # Phase 19 — CRM provider
    crm_provider: str = "mock"
    crm_api_key: str = ""

    # Phase 19 — Distributed rate limiting
    rate_limit_backend: str = "memory"  # "memory" or "redis"

    # Phase 14A — Outbox worker
    outbox_poll_interval_seconds: int = 5
    outbox_batch_size: int = 10
    outbox_max_attempts: int = 5
    outbox_lease_seconds: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT

    @field_validator("app_secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info: Any) -> str:
        if info.data.get("app_env") == Environment.PRODUCTION and v == "change-me-to-a-random-secret":
            raise ValueError("APP_SECRET_KEY must be set to a secure random value in production")
        return v

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str, info: Any) -> str:
        if info.data.get("app_env") == Environment.PRODUCTION and v == "change-me-to-a-random-jwt-secret":
            raise ValueError("JWT_SECRET_KEY must be set to a secure random value in production")
        return v


def get_settings() -> Settings:
    """Create and return application settings."""
    return Settings()
