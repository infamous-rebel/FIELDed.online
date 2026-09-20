"""Correlation ID middleware.

Binds request_id and correlation_id to the structured log context
for the duration of the request.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging import bind_request_context, clear_request_context


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind request/correlation IDs to the log context per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = getattr(request.state, "request_id", None)
        correlation_id = request.headers.get("X-Correlation-ID") or request_id

        if request_id:
            bind_request_context(request_id=request_id, correlation_id=correlation_id)

        try:
            response = await call_next(request)
            if correlation_id:
                response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            clear_request_context()
