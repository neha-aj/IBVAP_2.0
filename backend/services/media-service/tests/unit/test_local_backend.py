from pathlib import Path

import pytest

from app.storage.local_backend import LocalStorageBackend


@pytest.mark.asyncio
async def test_save_writes_file_and_returns_url_path(tmp_path: Path) -> None:
    backend = LocalStorageBackend(str(tmp_path), url_prefix="/media")

    url = await backend.save(subdir="snapshots/CAM-01/2026-01-01", filename="snapshot.jpg", data=b"jpegbytes")

    assert url.startswith("/media/snapshots/CAM-01/2026-01-01/")
    assert url.endswith("_snapshot.jpg")

    # The file must actually exist at the filesystem path the URL implies.
    relative = url.removeprefix("/media/")
    assert (tmp_path / relative).read_bytes() == b"jpegbytes"


@pytest.mark.asyncio
async def test_save_generates_unique_filenames_for_same_name(tmp_path: Path) -> None:
    backend = LocalStorageBackend(str(tmp_path), url_prefix="/media")

    url1 = await backend.save(subdir="snapshots/CAM-01", filename="snapshot.jpg", data=b"a")
    url2 = await backend.save(subdir="snapshots/CAM-01", filename="snapshot.jpg", data=b"b")

    assert url1 != url2


@pytest.mark.asyncio
async def test_url_prefix_trailing_slash_is_normalized(tmp_path: Path) -> None:
    backend = LocalStorageBackend(str(tmp_path), url_prefix="/media/")

    url = await backend.save(subdir="snapshots", filename="x.jpg", data=b"a")

    assert "//" not in url.removeprefix("/")


@pytest.mark.asyncio
async def test_no_url_prefix_returns_raw_filesystem_path(tmp_path: Path) -> None:
    """Phase 2 M23 -- camera source uploads: Ingestion Service reads this
    path straight off disk, so it must not come back as a `/media/...` URL
    the way every other call site's stored file does."""
    backend = LocalStorageBackend(str(tmp_path))

    path = await backend.save(subdir="uploads/CAM-01", filename="video.mp4", data=b"videobytes")

    assert not path.startswith("/media")
    assert Path(path).is_absolute() or Path(path).exists()
    assert Path(path).read_bytes() == b"videobytes"
