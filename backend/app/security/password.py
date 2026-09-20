"""Password hashing using bcrypt.

Provider-agnostic: bcrypt is a local hashing algorithm with no
external service dependency.
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    bcrypt has a 72-byte limit. Passwords are hashed as-is up to that limit.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt hash as a string.
    """
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        password: The plaintext password to verify.
        hashed_password: The bcrypt hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    password_bytes = password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)
