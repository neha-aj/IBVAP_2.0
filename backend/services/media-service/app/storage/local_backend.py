import os
import uuid
from pathlib import Path


class LocalStorageBackend:
    """Writes to a local Docker volume (`MEDIA_ROOT`), per SAS §7 Phase 1
    storage architecture. Implements `StorageBackend`.

    With `url_prefix` set, returns a URL path (e.g.
    `/media/snapshots/CAM-01/2026-09-05/<uuid>.jpg`) resolvable directly by
    nginx's static `/media/` alias -- for snapshots/recordings, media a
    browser fetches directly.

    Without it (`url_prefix=None`), returns the raw filesystem path
    instead -- for camera source uploads (Phase 2 M23), which Ingestion
    Service reads straight off disk via `cv2.VideoCapture(path)`, never
    over HTTP, so a URL would be the wrong shape entirely (see
    `camera_worker.py`'s own "it's a filesystem path, not a [URL]"
    comment)."""

    def __init__(self, root: str, *, url_prefix: str | None = None) -> None:
        self._root = Path(root)
        self._url_prefix = url_prefix.rstrip("/") if url_prefix else None

    async def save(self, *, subdir: str, filename: str, data: bytes) -> str:
        target_dir = self._root / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
        target_path = target_dir / safe_name
        target_path.write_bytes(data)
        if self._url_prefix is None:
            return str(target_path)
        return f"{self._url_prefix}/{subdir}/{safe_name}"
