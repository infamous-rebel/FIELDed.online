"""Shared API dependencies."""

from __future__ import annotations

# Re-export commonly used dependencies for convenience
from app.security.authorization import (
    get_current_user,
    get_optional_user,
    require_business_member,
    require_business_role,
    require_customer,
    tenant_scope,
)

__all__ = [
    "get_current_user",
    "get_optional_user",
    "require_customer",
    "require_business_member",
    "require_business_role",
    "tenant_scope",
]
