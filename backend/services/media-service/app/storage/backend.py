from typing import Protocol


class StorageBackend(Protocol):
    """Minimal interface for persisting a media blob (SAS §7: "abstracted
    behind a StorageBackend interface... so swapping to S3/MinIO in a later
    phase touches only the Media Storage Service's backend implementation").
    Mirrors `camera-service/app/storage/backend.py`'s own interface, which
    predates this service and will eventually proxy here instead (see that
    file's docstring) -- not part of this milestone's scope, noted in
    the README."""

    async def save(self, *, subdir: str, filename: str, data: bytes) -> str:
        """Persists `data` and returns a URL path resolvable under the
        service's `media_url_prefix` (not a filesystem path)."""
        ...
