"""Unit tests for password hashing."""

from __future__ import annotations

from app.security.password import hash_password, verify_password


class TestPasswordHashing:
    """Test bcrypt password hashing."""

    def test_hash_and_verify(self):
        """Password can be hashed and verified."""
        password = "secure_password_123"
        hashed = hash_password(password)

        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        """Wrong password does not verify."""
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_for_same_password(self):
        """Same password produces different hashes (different salts)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        # Both should still verify
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True

    def test_empty_password(self):
        """Empty password can be hashed and verified."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("not_empty", hashed) is False

    def test_long_password(self):
        """Long passwords are handled correctly."""
        password = "a" * 200
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_unicode_password(self):
        """Unicode passwords are handled correctly."""
        password = "pässwörd_日本語"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
