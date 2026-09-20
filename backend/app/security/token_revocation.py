"""Token revocation for logout and security.

Maintains a set of revoked JWT JTIs (JWT IDs).
In production, this should be backed by Redis for cross-instance sharing.
For now, uses an in-memory set with automatic expiry cleanup.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime


class TokenRevocationStore:
    """In-memory store for revoked JWT token IDs.

    Thread-safe. Each entry has a TTL matching the original token's
    remaining lifetime, so the store self-cleans over time.
    """

    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}  # jti -> expiry timestamp
        self._lock = threading.Lock()

    def revoke(self, jti: str, expires_at: datetime) -> None:
        """Mark a token JTI as revoked until it would have expired."""
        expiry_ts = expires_at.timestamp()
        with self._lock:
            self._revoked[jti] = expiry_ts

    def is_revoked(self, jti: str) -> bool:
        """Check if a token JTI has been revoked."""
        with self._lock:
            expiry = self._revoked.get(jti)
            if expiry is None:
                return False
            # Auto-clean expired entries
            if time.time() > expiry:
                del self._revoked[jti]
                return False
            return True

    def cleanup(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        now = time.time()
        with self._lock:
            expired = [jti for jti, exp in self._revoked.items() if now > exp]
            for jti in expired:
                del self._revoked[jti]
            return len(expired)

    @property
    def size(self) -> int:
        """Number of currently revoked tokens."""
        with self._lock:
            return len(self._revoked)


# Global singleton
revocation_store = TokenRevocationStore()
