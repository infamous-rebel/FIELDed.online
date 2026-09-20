"""FIELDed exception hierarchy.

All domain and application exceptions inherit from FieldedError.
HTTP-facing exceptions carry a status_code and machine-readable error_code.
"""

from __future__ import annotations

from typing import Any


class FieldedError(Exception):
    """Base exception for all FIELDed errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class DomainError(FieldedError):
    """Base for domain-level business rule violations."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "DOMAIN_ERROR")
        kwargs.setdefault("status_code", 422)
        super().__init__(message, **kwargs)


class NotFoundError(FieldedError):
    """Requested resource does not exist."""

    def __init__(self, message: str = "Resource not found", **kwargs: Any) -> None:
        super().__init__(message, error_code="NOT_FOUND", status_code=404, **kwargs)


class ConflictError(FieldedError):
    """Operation conflicts with existing state."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_code="CONFLICT", status_code=409, **kwargs)


class AuthorizationError(FieldedError):
    """Actor is not permitted to perform this action."""

    def __init__(self, message: str = "Not authorized", **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "NOT_AUTHORIZED")
        kwargs.setdefault("status_code", 403)
        super().__init__(message, **kwargs)


class AuthenticationError(FieldedError):
    """Actor is not authenticated or credentials are invalid."""

    def __init__(self, message: str = "Authentication required", **kwargs: Any) -> None:
        super().__init__(message, error_code="AUTHENTICATION_REQUIRED", status_code=401, **kwargs)


class ValidationError(FieldedError):
    """Input validation failed."""

    def __init__(self, message: str = "Validation failed", **kwargs: Any) -> None:
        super().__init__(message, error_code="VALIDATION_ERROR", status_code=422, **kwargs)


class StateTransitionError(DomainError):
    """Invalid state machine transition attempted."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_code="INVALID_STATE_TRANSITION", **kwargs)


class TenantIsolationError(AuthorizationError):
    """Cross-tenant access attempted."""

    def __init__(self, message: str = "Tenant isolation violation", **kwargs: Any) -> None:
        super().__init__(message, error_code="TENANT_ISOLATION_VIOLATION", **kwargs)
