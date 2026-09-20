"""Unit tests for authorization logic."""

from __future__ import annotations

import pytest

from app.domain.common.enums import BusinessMemberRole
from app.exceptions import AuthorizationError, TenantIsolationError


class TestAuthorization:
    """Test authorization helpers."""

    def test_business_member_role_hierarchy(self):
        """Verify role hierarchy ordering."""
        hierarchy = {
            BusinessMemberRole.OWNER: 3,
            BusinessMemberRole.ADMIN: 2,
            BusinessMemberRole.STAFF: 1,
        }
        assert hierarchy[BusinessMemberRole.OWNER] > hierarchy[BusinessMemberRole.ADMIN]
        assert hierarchy[BusinessMemberRole.ADMIN] > hierarchy[BusinessMemberRole.STAFF]

    def test_tenant_isolation_error_is_authorization_error(self):
        """TenantIsolationError inherits from AuthorizationError."""
        error = TenantIsolationError()
        assert isinstance(error, AuthorizationError)
        assert error.error_code == "TENANT_ISOLATION_VIOLATION"

    def test_authorization_error_status_code(self):
        """AuthorizationError returns 403."""
        error = AuthorizationError()
        assert error.status_code == 403

    def test_authentication_error_status_code(self):
        """AuthenticationError returns 401."""
        from app.exceptions import AuthenticationError
        error = AuthenticationError()
        assert error.status_code == 401
