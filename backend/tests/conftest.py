"""Test configuration and shared fixtures.

Provides:
- Async database session for tests (uses a test database)
- FastAPI test client via httpx
- Test data factories
- Application settings override for test environment

Key design: tests and HTTP endpoints share the SAME database session
so that flushed (uncommitted) data is visible to both.  After each test
the session is rolled back, keeping the database clean.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from contextvars import ContextVar

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.database import get_db_session
from app.domain.booking.models import Booking  # noqa: F401
from app.domain.business.models import BrainVersion, BusinessBrain, BusinessRule  # noqa: F401
from app.domain.common.base_model import Base

# Phase 14A — Communication, Notification, Outbox
from app.domain.communication.models import (  # noqa: F401
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    Communication,
    CommunicationAttempt,
    CommunicationAuditEvent,
    CommunicationRecipient,
    CommunicationTemplate,
    CommunicationTemplateVersion,
    CommunicationWebhook,
    CustomerCommunicationPreference,
)
from app.domain.enquiry.models import Conversation, Enquiry, Message  # noqa: F401

# Import all models so Base.metadata has them
from app.domain.identity.models import (  # noqa: F401
    Business,
    BusinessMember,
    BusinessProfile,
    CustomerProfile,
    User,
)
from app.domain.identity.token_models import (  # noqa: F401
    EmailVerification,
    MemberInvitation,  # noqa: F401
    PasswordResetToken,
)
from app.domain.invoice.models import Invoice, InvoiceLineItem  # noqa: F401
from app.domain.ledger.models import ServiceLedgerEntry  # noqa: F401
from app.domain.notification.models import Notification  # noqa: F401
from app.domain.outbox.models import OutboxEvent  # noqa: F401

# Phase 15 — Payments & Financial Operations
from app.domain.payment.models import Payment, PaymentAttempt  # noqa: F401
from app.domain.quote.models import Quote  # noqa: F401

# Phase 17 — Reviews & Trust
from app.domain.review.models import Review  # noqa: F401
from app.domain.service_execution.models import ServiceExecution  # noqa: F401
from app.domain.services.models import ServiceCategory, ServiceOffer  # noqa: F401

# Phase 14B — Voice / Call Agent foundation
from app.domain.voice.models import (  # noqa: F401
    CallAgentConfiguration,
    CampaignRecipient,
    CommunicationCampaign,
    VoiceCall,
    VoiceCallAttempt,
    VoiceCallEscalation,
    VoiceCallParticipant,
    VoiceCallSession,
)

# Test settings — use a dedicated test database. CI (and any other
# environment) supplies DATABASE_URL for its postgres service; the default
# matches docker/docker-compose.test.yml for local runs.
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://fielded:fielded@localhost:5433/fielded_test",
)

# ContextVar to share the current test session with the app dependency override
_test_session_var: ContextVar[AsyncSession | None] = ContextVar("_test_session_var", default=None)


def get_test_settings() -> Settings:
    """Create settings for the test environment."""
    os.environ["APP_ENV"] = "development"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    settings = Settings()
    return settings


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a test database engine (per-test, shares event loop with test)."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    # Clean slate: reset schema in separate transaction, then create tables
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    except Exception:
        pass  # Best-effort; first run may not need this

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up: best-effort schema reset
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    except Exception:
        pass

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session shared with HTTP endpoints.

    The session is stored in a ContextVar so the app's dependency
    override can return the SAME session.  This means flushed (but
    uncommitted) data is visible to both test code and endpoints.
    After the test, the session is rolled back.
    """
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        token = _test_session_var.set(session)
        yield session
        await session.rollback()
        _test_session_var.reset(token)


@pytest_asyncio.fixture
async def app(test_engine: AsyncEngine):
    """Create a FastAPI test application."""
    from unittest.mock import AsyncMock, patch

    import app.database as db_module
    from app.main import create_app

    settings = get_test_settings()

    # Pre-set the global engine so lifespan init_db doesn't create a second one
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    db_module._engine = test_engine
    db_module._session_factory = test_session_factory

    with patch("app.main.init_db"), patch("app.main.dispose_engine", new_callable=AsyncMock):
        app = create_app(settings)

        # Disable rate limiting in tests (all requests come from same IP)
        from app.middleware.rate_limit import RateLimitMiddleware

        app.user_middleware = [m for m in app.user_middleware if m.cls is not RateLimitMiddleware]

        # Override the database dependency to return the SAME session
        # that db_session created (via ContextVar)
        async def _override_get_db():
            session = _test_session_var.get()
            if session is not None:
                yield session
            else:
                # Fallback: create a new session (for lifespan/health checks)
                async with test_session_factory() as s:
                    yield s

        app.dependency_overrides[get_db_session] = _override_get_db

        yield app

        app.dependency_overrides.clear()

    # Clear globals without disposing the test engine (session fixture manages it)
    db_module._engine = None
    db_module._session_factory = None


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user with customer profile."""
    from app.security.password import hash_password

    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()

    profile = CustomerProfile(
        user_id=user.id,
        first_name="Test",
        last_name="User",
    )
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(user, attribute_names=["customer_profile"])

    return user


@pytest_asyncio.fixture
async def second_user(db_session: AsyncSession) -> User:
    """Create a second test user for cross-tenant tests."""
    from app.security.password import hash_password

    user = User(
        email=f"second-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()

    profile = CustomerProfile(
        user_id=user.id,
        first_name="Second",
        last_name="User",
    )
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(user, attribute_names=["customer_profile"])

    return user


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user: User) -> dict[str, str]:
    """Get authorization headers for the test user."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "testpassword123"},
    )
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture
async def second_auth_headers(client: AsyncClient, second_user: User) -> dict[str, str]:
    """Get authorization headers for the second user."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": second_user.email, "password": "testpassword123"},
    )
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}
