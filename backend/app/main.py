"""FastAPI application factory.

Creates and configures the FastAPI application with all middleware,
routes, exception handlers, and lifecycle events.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import Settings, get_settings
from app.database import dispose_engine, get_session_factory, init_db
from app.exceptions import FieldedError
from app.logging import get_logger, setup_logging
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.tenant import TenantMiddleware

logger = get_logger(__name__)

# Outbox worker control: set in lifespan, cancelled on shutdown.
_outbox_task: asyncio.Task | None = None


async def _outbox_worker_loop() -> None:
    """Background outbox event processor.

    Polls every 15 seconds for pending outbox events and processes them
    through the orchestration pipeline (notifications, communications).
    Runs inside the FastAPI process — no separate worker needed for
    development / single-instance deployments.
    """
    from app.adapters import ProviderFactory
    from app.domain.communication.orchestration import OrchestrationService
    from app.config import get_settings
    from app.domain.voice.outbox_integration import VoiceEventOrchestrator
    from app.workers import process_outbox_events

    settings = get_settings()
    factory = ProviderFactory.from_settings(settings)

    logger.info("outbox_worker_started", interval_seconds=15)

    while True:
        try:
            await asyncio.sleep(15)

            session_factory = get_session_factory()
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
                if processed > 0:
                    logger.info("outbox_worker_processed", count=processed)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("outbox_worker_error")
            await asyncio.sleep(30)  # Back off on error

    logger.info("outbox_worker_stopped")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: startup and shutdown."""
    global _outbox_task

    settings: Settings = app.state.settings

    setup_logging(
        json_output=settings.is_production,
        log_level="DEBUG" if settings.app_debug else "INFO",
    )

    init_db(settings)
    logger.info("application_started", app_name=settings.app_name, env=settings.app_env)

    # Start the outbox background worker
    _outbox_task = asyncio.create_task(_outbox_worker_loop())

    yield

    # Shutdown: cancel the outbox worker
    if _outbox_task is not None:
        _outbox_task.cancel()
        try:
            await _outbox_task
        except asyncio.CancelledError:
            pass
        _outbox_task = None

    await dispose_engine()
    logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    app.state.settings = settings

    # Middleware (order matters: outermost first — CORS must be first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers
    @app.exception_handler(FieldedError)
    async def fielded_error_handler(request: Request, exc: FieldedError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                    "request_id": request_id,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error("unhandled_exception", error=str(exc), request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                    "request_id": request_id,
                },
            },
        )

    # Routes
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
