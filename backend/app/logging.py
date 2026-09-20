"""Structured JSON logging with request correlation.

Uses structlog for structured output. Every log entry includes
timestamp, level, event, and optional request_id/correlation_id.
"""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(*, json_output: bool = True, log_level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Args:
        json_output: If True, output JSON lines. If False, human-readable console format.
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Suppress overly verbose loggers
    for name in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


def bind_request_context(request_id: str, correlation_id: str | None = None) -> None:
    """Bind request/correlation IDs to the current log context."""
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        correlation_id=correlation_id or request_id,
    )


def clear_request_context() -> None:
    """Clear request/correlation IDs from the log context."""
    structlog.contextvars.clear_contextvars()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger bound to the given name."""
    return structlog.get_logger(name)
