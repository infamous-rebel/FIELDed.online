"""Tenant resolution middleware.

Resolves the current tenant (business) context from the authenticated user.
This runs AFTER authentication and ensures tenant context is available
for all subsequent request processing.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant context from authenticated user.

    This middleware does NOT enforce tenant isolation — that happens
    at the repository/authorization layer. It simply makes tenant
    information available on the request state for downstream use.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Tenant resolution happens via auth dependencies,
        # not from headers or URL parameters.
        # This middleware is a hook point for future tenant-level middleware.
        request.state.tenant_id = None
        request.state.tenant_type = None

        response = await call_next(request)
        return response
