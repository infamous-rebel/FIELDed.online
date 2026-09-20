"""Unit tests for token revocation store."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.security.token_revocation import TokenRevocationStore


class TestTokenRevocationStore:
    """Tests for the in-memory token revocation store."""

    def test_revoke_and_check(self):
        """Revoked tokens are detected."""
        store = TokenRevocationStore()
        jti = "test-jti-1"
        expires = datetime.now(UTC) + timedelta(hours=1)

        store.revoke(jti, expires)
        assert store.is_revoked(jti) is True

    def test_non_revoked_token(self):
        """Non-revoked tokens pass through."""
        store = TokenRevocationStore()
        assert store.is_revoked("nonexistent-jti") is False

    def test_expired_revocation_auto_cleaned(self):
        """Expired revocations are auto-cleaned."""
        store = TokenRevocationStore()
        jti = "expired-jti"
        # Set expiry in the past
        expires = datetime.now(UTC) - timedelta(seconds=1)

        store.revoke(jti, expires)
        # Should be considered expired and cleaned
        assert store.is_revoked(jti) is False

    def test_cleanup_removes_expired(self):
        """Manual cleanup removes expired entries."""
        store = TokenRevocationStore()
        # Add expired entry
        store.revoke("expired", datetime.now(UTC) - timedelta(hours=1))
        # Add valid entry
        store.revoke("valid", datetime.now(UTC) + timedelta(hours=1))

        removed = store.cleanup()
        assert removed == 1
        assert store.size == 1
        assert store.is_revoked("valid") is True

    def test_size_property(self):
        """Size reflects active revocations."""
        store = TokenRevocationStore()
        assert store.size == 0

        store.revoke("j1", datetime.now(UTC) + timedelta(hours=1))
        store.revoke("j2", datetime.now(UTC) + timedelta(hours=1))
        assert store.size == 2

    def test_multiple_revocations(self):
        """Multiple tokens can be revoked independently."""
        store = TokenRevocationStore()
        expires = datetime.now(UTC) + timedelta(hours=1)

        store.revoke("jti-1", expires)
        store.revoke("jti-2", expires)

        assert store.is_revoked("jti-1") is True
        assert store.is_revoked("jti-2") is True
        assert store.is_revoked("jti-3") is False
