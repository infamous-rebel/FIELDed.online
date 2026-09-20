"""Object storage provider abstract base class.

Defines the interface for file/object storage integrations.
Concrete implementations can wrap S3, GCS, Azure Blob, local filesystem, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StoredObject:
    """Metadata for a stored object."""

    key: str
    size: int
    content_type: str
    url: str | None = None


class StorageProvider(ABC):
    """Abstract base class for object storage providers."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Upload an object.

        Args:
            key: The object key/path.
            data: The file content as bytes.
            content_type: MIME type.

        Returns:
            Metadata for the stored object.
        """
        ...

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download an object.

        Args:
            key: The object key/path.

        Returns:
            The file content as bytes.
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an object.

        Args:
            key: The object key/path.
        """
        ...

    @abstractmethod
    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get a temporary URL for an object.

        Args:
            key: The object key/path.
            expires_in: URL expiry in seconds.

        Returns:
            A presigned URL.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this storage provider."""
        ...
