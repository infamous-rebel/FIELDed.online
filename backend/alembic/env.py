"""Alembic environment configuration for async SQLAlchemy."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.domain.common.base_model import Base

# Import all models so Alembic sees them
from app.domain.identity.models import (  # noqa: F401
    User,
    CustomerProfile,
    Business,
    BusinessProfile,
    BusinessMember,
)
from app.domain.business.models import BusinessBrain, BrainVersion, BusinessRule  # noqa: F401
from app.domain.services.models import ServiceCategory, ServiceOffer  # noqa: F401
from app.domain.enquiry.models import Enquiry, Conversation, Message  # noqa: F401
from app.domain.communication.models import (  # noqa: F401
    Communication,
    CommunicationRecipient,
    CommunicationAttempt,
    CommunicationTemplate,
    CommunicationTemplateVersion,
    BusinessCommunicationChannel,
    BusinessCommunicationPurpose,
    CustomerCommunicationPreference,
    CommunicationWebhook,
    CommunicationAuditEvent,
)
from app.domain.quote.models import Quote  # noqa: F401
from app.domain.booking.models import Booking  # noqa: F401
from app.domain.service_execution.models import ServiceExecution  # noqa: F401
from app.domain.invoice.models import Invoice, InvoiceLineItem  # noqa: F401
from app.domain.ledger.models import ServiceLedgerEntry  # noqa: F401
from app.domain.payment.models import Payment, PaymentAttempt  # noqa: F401
from app.domain.notification.models import Notification  # noqa: F401
from app.domain.outbox.models import OutboxEvent  # noqa: F401
from app.domain.review.models import Review  # noqa: F401
from app.domain.voice.models import (  # noqa: F401
    VoiceCall,
    VoiceCallParticipant,
    VoiceCallAttempt,
    VoiceCallSession,
    VoiceCallEscalation,
    CallAgentConfiguration,
    CommunicationCampaign,
    CampaignRecipient,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override URL from settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations with an active connection.

    ``ensure_version_table`` must run INSIDE ``context.begin_transaction()``:
    executing DDL on the raw connection first would auto-begin a transaction,
    making Alembic's own ``begin_transaction()`` a no-op that never commits —
    and the whole migration chain would be rolled back when the connection
    closes.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        ensure_version_table(connection)
        context.run_migrations()


def ensure_version_table(connection) -> None:
    """Ensure alembic_version can hold this repository's revision ids.

    Alembic creates ``alembic_version.version_num`` as VARCHAR(32), but
    this repository uses descriptive revision identifiers (e.g.
    ``009_phase13_service_execution_invoice_ledger``, 45 characters).
    Pre-create the table wide enough (and widen if it already exists)
    so the historical migration chain remains runnable unmodified.
    """
    connection.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL)")
    )
    connection.execute(
        text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    )


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    section = config.get_section(config.config_ini_section, {})
    url = section.get("sqlalchemy.url", "")

    # Handle asyncpg SSL compatibility: strip sslmode/channel_binding from URL
    # and pass via connect_args instead
    connect_args: dict = {}
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    sslmode = query_params.pop("sslmode", [None])[0]
    query_params.pop("channel_binding", None)

    if sslmode and sslmode != "disable":
        connect_args["ssl"] = sslmode

    new_query = urlencode(query_params, doseq=True)
    clean_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))

    section["sqlalchemy.url"] = clean_url

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
