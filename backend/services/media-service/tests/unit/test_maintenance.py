from pathlib import Path

from app.api.maintenance import _delete_files, _disk_path


def _make(root: Path, rel: str, size: int = 10) -> str:
    """Creates a file under `root` and returns its stored URL-style path."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return f"/media/{rel}"


def test_disk_path_maps_a_stored_url_to_its_file(tmp_path: Path) -> None:
    target = _disk_path(tmp_path, "/media", "/media/snapshots/CAM/2026-01-01/a.jpg")

    assert target == (tmp_path / "snapshots/CAM/2026-01-01/a.jpg").resolve()


def test_disk_path_refuses_traversal_out_of_the_media_root(tmp_path: Path) -> None:
    """A corrupt or hostile row must never aim a delete at another folder."""
    assert _disk_path(tmp_path, "/media", "/media/../../etc/passwd") is None
    assert _disk_path(tmp_path, "/media", "/media/snapshots/../../outside.txt") is None


def test_disk_path_refuses_paths_without_the_media_prefix(tmp_path: Path) -> None:
    assert _disk_path(tmp_path, "/media", "/etc/passwd") is None
    assert _disk_path(tmp_path, "/media", "snapshots/a.jpg") is None


def test_disk_path_refuses_the_root_itself(tmp_path: Path) -> None:
    assert _disk_path(tmp_path, "/media", "/media/") is None


def test_delete_files_removes_files_and_reports_bytes(tmp_path: Path) -> None:
    a = _make(tmp_path, "snapshots/CAM/2026-01-01/a.jpg", size=100)
    b = _make(tmp_path, "snapshots/CAM/2026-01-01/b.jpg", size=50)

    freed, missing = _delete_files(tmp_path, "/media", [a, b])

    assert (freed, missing) == (150, 0)
    assert not (tmp_path / "snapshots/CAM/2026-01-01/a.jpg").exists()


def test_delete_files_counts_an_already_missing_file_without_failing(tmp_path: Path) -> None:
    real = _make(tmp_path, "snapshots/CAM/2026-01-01/a.jpg", size=7)

    freed, missing = _delete_files(tmp_path, "/media", [real, "/media/snapshots/CAM/2026-01-01/ghost.jpg"])

    assert (freed, missing) == (7, 1)


def test_delete_files_tidies_up_empty_folders_but_never_the_root(tmp_path: Path) -> None:
    stored = _make(tmp_path, "snapshots/CAM/2026-01-01/a.jpg")

    _delete_files(tmp_path, "/media", [stored])

    assert not (tmp_path / "snapshots/CAM/2026-01-01").exists()
    assert not (tmp_path / "snapshots/CAM").exists()
    assert tmp_path.exists()


def test_delete_files_leaves_a_folder_that_still_has_other_files(tmp_path: Path) -> None:
    gone = _make(tmp_path, "snapshots/CAM/2026-01-01/a.jpg")
    kept = _make(tmp_path, "snapshots/CAM/2026-01-01/keep.jpg")

    _delete_files(tmp_path, "/media", [gone])

    assert (tmp_path / "snapshots/CAM/2026-01-01/keep.jpg").exists()
    assert kept.endswith("keep.jpg")


def test_delete_files_ignores_a_row_that_points_outside_the_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_evidence.txt"
    outside.write_bytes(b"do not delete")
    media_root = tmp_path / "media"
    media_root.mkdir()

    freed, missing = _delete_files(media_root, "/media", ["/media/../outside_evidence.txt"])

    assert outside.exists()
    assert (freed, missing) == (0, 0)


# --- purge by id -----------------------------------------------------------

import uuid  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from app.api import maintenance  # noqa: E402
from app.core.config import Settings  # noqa: E402


class _FakeSession:
    def __init__(self, rows) -> None:
        self._rows = rows
        self.deleted = False
        self.committed = False

    async def execute(self, stmt):
        if "DELETE" in str(stmt).upper():
            self.deleted = True
            return SimpleNamespace()
        return SimpleNamespace(all=lambda: self._rows)

    async def commit(self) -> None:
        self.committed = True


def _settings(root: Path) -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
                    internal_service_token="t", media_root=str(root))


@pytest.mark.asyncio
async def test_purge_by_id_deletes_the_files_and_rows_of_the_given_snapshots_only(tmp_path: Path) -> None:
    target = _make(tmp_path, "snapshots/CAM/2026-01-01/a.jpg", size=300)
    keep = _make(tmp_path, "snapshots/CAM/2026-01-01/keep.jpg", size=999)
    row = SimpleNamespace(id=uuid.uuid4(), file_path=target)
    session = _FakeSession([row])

    result = await maintenance.purge_snapshots_by_id(
        maintenance.SnapshotIdsPurgeRequest(ids=[row.id]), session, _settings(tmp_path)
    )

    assert (result.snapshots_removed, result.bytes_freed) == (1, 300)
    assert session.deleted and session.committed
    assert not (tmp_path / "snapshots/CAM/2026-01-01/a.jpg").exists()
    assert (tmp_path / "snapshots/CAM/2026-01-01/keep.jpg").exists() and keep.endswith("keep.jpg")


@pytest.mark.asyncio
async def test_purge_by_id_with_no_ids_or_unknown_ids_removes_nothing(tmp_path: Path) -> None:
    empty = await maintenance.purge_snapshots_by_id(
        maintenance.SnapshotIdsPurgeRequest(ids=[]), _FakeSession([]), _settings(tmp_path)
    )
    unknown_session = _FakeSession([])
    unknown = await maintenance.purge_snapshots_by_id(
        maintenance.SnapshotIdsPurgeRequest(ids=[uuid.uuid4()]), unknown_session, _settings(tmp_path)
    )

    assert empty.snapshots_removed == 0 and unknown.snapshots_removed == 0
    assert not unknown_session.deleted


def test_purge_by_id_request_is_bounded() -> None:
    with pytest.raises(Exception):
        maintenance.SnapshotIdsPurgeRequest(ids=[uuid.uuid4() for _ in range(5001)])
