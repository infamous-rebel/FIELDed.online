"""Standalone CLI entry point for the outbox worker.

Usage:
    python -m app.workers.outbox

Runs a single processing pass, then exits.
For continuous operation, wrap in a loop or use a scheduler.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters import ProviderFactory
from app.config import get_settings
from app.domain.communication.orchestration import OrchestrationService
from app.domain.voice.outbox_integration import VoiceEventOrchestrator
from app.workers import process_outbox_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run a single outbox processing pass."""
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
    )
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    # Build providers
    factory = ProviderFactory.from_settings(settings)

    async with session_factory() as session:
        orchestrator = OrchestrationService(
            session,
            email_provider=factory.email_provider,
            sms_provider=factory.sms_provider,
            voice_provider=factory.voice_provider,
            whatsapp_provider=factory.whatsapp_provider,
            push_provider=factory.push_provider,
        )
        voice_orchestrator = VoiceEventOrchestrator(session)

        processed = await process_outbox_events(
            session,
            orchestrator=orchestrator,
            batch_size=settings.outbox_batch_size,
            lease_seconds=settings.outbox_lease_seconds,
            max_attempts=settings.outbox_max_attempts,
            voice_orchestrator=voice_orchestrator,
        )

    await engine.dispose()

    logger.info("Outbox worker pass complete. Processed %d events.", processed)


if __name__ == "__main__":
    asyncio.run(main())
