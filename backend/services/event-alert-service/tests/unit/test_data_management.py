import datetime as dt
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ibvap_common.errors import ApiError, ConflictError

from app.api import data_management as dm
from app.api import events as events_api
from app.core.config import Settings
from app.schemas.event import to_event_detail, to_event_read


def _settings() -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
                    internal_service_token="t")


# --- request validation -----------------------------------------------------

def test_reset_requires_the_exact_confirmation_word() -> None:
    with pytest.raises(ValidationError):
        dm.ResetRequest(confirm="reset")
    with pytest.raises(ValidationError):
        dm.ResetRequest(confirm="yes")
    with pytest.raises(ValidationError):
        dm.ResetRequest()  # type: ignore[call-arg]
    assert dm.ResetRequest(confirm="RESET").older_than_days is None


def test_reset_rejects_a_nonsensical_age() -> None:
    for bad in (0, -5, 100000):
        with pytest.raises(ValidationError):
            dm.ResetRequest(olderThanDays=bad, confirm="RESET")
    assert dm.ResetRequest(olderThanDays=30, confirm="RESET").older_than_days == 30


def test_cutoff_is_now_for_everything_and_n_days_back_otherwise() -> None:
    now = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.UTC)

    assert dm.compute_cutoff(now, None) == now
    assert dm.compute_cutoff(now, 7) == now - dt.timedelta(days=7)


# --- reset behaviour --------------------------------------------------------

class _FakeSession:
    def __init__(self, counts: list[int], *, fail_on_execute: bool = False) -> None:
        self._counts = list(counts)
        self.executed: list[str] = []
        self.committed = False
        self.rolled_back = False
        self._fail = fail_on_execute

    async def scalar(self, stmt):
        return self._counts.pop(0)

    async def execute(self, stmt):
        self.executed.append(str(stmt))
        if self._fail:
            raise RuntimeError("db down")
        return SimpleNamespace(rowcount=42)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture(autouse=True)
def _reset_job(monkeypatch):
    """Fresh idle job state per test, and no real media-service call."""
    monkeypatch.setattr(dm, "_job", dm._CleanupJob())
    calls: list[dt.datetime] = []

    async def fake_cleanup(settings, before):
        calls.append(before)
        dm._job.status = "done"

    monkeypatch.setattr(dm, "_run_media_cleanup", fake_cleanup)
    return calls


@pytest.mark.asyncio
async def test_reset_everything_truncates_and_starts_evidence_cleanup(_reset_job) -> None:
    session = _FakeSession(counts=[7, 100])  # alerts, events

    result = await dm.reset(dm.ResetRequest(confirm="RESET"), session, _settings(), None)

    assert (result.alerts_removed, result.events_removed) == (7, 100)
    assert any("TRUNCATE" in stmt for stmt in session.executed)
    assert session.committed
    assert result.cleanup.status == "running"
    await dm._job.task
    assert len(_reset_job) == 1  # the evidence purge was kicked off once


@pytest.mark.asyncio
async def test_reset_older_than_deletes_only_old_rows_and_purges_evidence_before_the_same_cutoff(_reset_job) -> None:
    session = _FakeSession(counts=[3])  # alerts older than the cutoff

    before = dt.datetime.now(dt.UTC)
    result = await dm.reset(dm.ResetRequest(olderThanDays=30, confirm="RESET"), session, _settings(), None)

    assert not any("TRUNCATE" in stmt for stmt in session.executed)
    assert any("DELETE" in stmt.upper() for stmt in session.executed)
    assert (result.alerts_removed, result.events_removed) == (3, 42)
    await dm._job.task
    cutoff = _reset_job[0]
    assert before - dt.timedelta(days=30, seconds=5) <= cutoff <= before - dt.timedelta(days=30) + dt.timedelta(seconds=5)


@pytest.mark.asyncio
async def test_a_failed_delete_rolls_back_and_starts_no_cleanup(_reset_job) -> None:
    session = _FakeSession(counts=[1, 1], fail_on_execute=True)

    with pytest.raises(ApiError) as excinfo:
        await dm.reset(dm.ResetRequest(confirm="RESET"), session, _settings(), None)
    assert excinfo.value.status_code == 500

    assert session.rolled_back and not session.committed
    assert _reset_job == []
    assert dm._job.status == "idle"


@pytest.mark.asyncio
async def test_a_second_reset_is_refused_while_cleanup_is_running() -> None:
    dm._job.status = "running"

    with pytest.raises(ConflictError):
        await dm.reset(dm.ResetRequest(confirm="RESET"), _FakeSession(counts=[0, 0]), _settings(), None)


# --- event schema ------------------------------------------------------------

def _event(**overrides):
    base = dict(
        id="e1", created_at=dt.datetime(2026, 9, 20, tzinfo=dt.UTC), camera_id="CAM-1", camera_name="Gate",
        event_type="Loitering Detected", object_type="person", location="North", severity="medium",
        status="active", description=None, recording_id=None, snapshot_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_event_read_now_carries_the_camera_id() -> None:
    read = to_event_read(_event())

    assert read.camera_id == "CAM-1"
    assert read.model_dump(by_alias=True)["cameraId"] == "CAM-1"


def test_event_detail_still_builds_with_camera_id_in_both_parents() -> None:
    detail = to_event_detail(_event(), _settings())

    assert detail.camera_id == "CAM-1"


def test_filter_options_route_is_declared_before_the_event_id_route() -> None:
    """Otherwise "filter-options" would be captured as an event id."""
    paths = [route.path for route in events_api.router.routes]

    assert paths.index("/api/v1/events/filter-options") < paths.index("/api/v1/events/{event_id}")


# --- "Direction Observed images only" mode ---------------------------------

import uuid  # noqa: E402


def test_images_only_mode_is_an_accepted_option_and_nothing_else_is() -> None:
    assert dm.ResetRequest(only="direction_images", confirm="RESET").only == "direction_images"
    assert dm.ResetRequest(confirm="RESET").only is None
    with pytest.raises(ValidationError):
        dm.ResetRequest(only="everything_else", confirm="RESET")


@pytest.mark.asyncio
async def test_images_only_reset_deletes_no_events_or_alerts_and_starts_the_image_job(monkeypatch) -> None:
    started: list[object] = []

    async def fake_cleanup(settings, before):
        started.append(before)
        dm._job.status = "done"

    monkeypatch.setattr(dm, "_run_direction_image_cleanup", fake_cleanup)
    session = _FakeSession(counts=[1234])  # Direction Observed events that still have an image

    result = await dm.reset(dm.ResetRequest(only="direction_images", confirm="RESET"), session, _settings(), None)

    assert (result.events_removed, result.alerts_removed) == (0, 0)
    assert session.executed == []  # no TRUNCATE, no DELETE -- nothing touched synchronously
    assert not session.committed
    assert result.cleanup.status == "running" and result.cleanup.snapshots_total == 1234
    await dm._job.task
    assert started == [None]  # "all" -> no cutoff


@pytest.mark.asyncio
async def test_images_only_reset_with_an_age_limits_the_cleanup_to_older_events(monkeypatch) -> None:
    started: list[object] = []

    async def fake_cleanup(settings, before):
        started.append(before)

    monkeypatch.setattr(dm, "_run_direction_image_cleanup", fake_cleanup)

    await dm.reset(
        dm.ResetRequest(only="direction_images", olderThanDays=7, confirm="RESET"),
        _FakeSession(counts=[5]), _settings(), None,
    )
    await dm._job.task

    assert started[0] is not None


class _BatchSession:
    """Serves successive batches of (event id, snapshot id) rows, records the
    UPDATE that detaches them, like the real session would."""

    def __init__(self, batches, log) -> None:
        self._batches = batches
        self._log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def execute(self, stmt):
        text_ = str(stmt).upper()
        if text_.startswith("UPDATE"):
            self._log.append("update")
            return SimpleNamespace()
        batch = self._batches.pop(0) if self._batches else []
        return SimpleNamespace(all=lambda: batch)

    async def commit(self) -> None:
        self._log.append("commit")


class _FakeMediaClient:
    def __init__(self, posted, *, fail=False) -> None:
        self._posted = posted
        self._fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, json, headers):
        self._posted.append((url, json["ids"], headers))
        if self._fail:
            raise RuntimeError("media down")
        n = len(json["ids"])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"snapshotsRemoved": n, "bytesFreed": n * 100})


def _rows(n):
    return [SimpleNamespace(id=uuid.uuid4(), snapshot_id=uuid.uuid4()) for _ in range(n)]


@pytest.mark.asyncio
async def test_image_cleanup_works_through_every_batch_and_detaches_each(monkeypatch) -> None:
    log: list[str] = []
    posted: list = []
    batches = [_rows(3), _rows(2)]
    monkeypatch.setattr(dm, "get_session_factory", lambda: (lambda: _BatchSession(batches, log)))
    monkeypatch.setattr(dm.httpx, "AsyncClient", lambda **kw: _FakeMediaClient(posted))
    dm._job.status = "running"

    await dm._run_direction_image_cleanup(_settings(), None)

    assert [len(ids) for _url, ids, _h in posted] == [3, 2]
    assert posted[0][0].endswith("/internal/media/snapshots/purge")
    assert posted[0][2] == {"X-Internal-Token": "t"}
    assert log == ["update", "commit", "update", "commit"]  # every batch's events were detached
    assert (dm._job.status, dm._job.snapshots_removed, dm._job.bytes_freed) == ("done", 5, 500)


@pytest.mark.asyncio
async def test_image_cleanup_with_nothing_to_remove_finishes_immediately(monkeypatch) -> None:
    posted: list = []
    monkeypatch.setattr(dm, "get_session_factory", lambda: (lambda: _BatchSession([], [])))
    monkeypatch.setattr(dm.httpx, "AsyncClient", lambda **kw: _FakeMediaClient(posted))

    await dm._run_direction_image_cleanup(_settings(), None)

    assert posted == [] and dm._job.status == "done"


@pytest.mark.asyncio
async def test_image_cleanup_failure_is_reported_and_never_detaches_events_whose_files_survived(monkeypatch) -> None:
    log: list[str] = []
    monkeypatch.setattr(dm, "get_session_factory", lambda: (lambda: _BatchSession([_rows(2)], log)))
    monkeypatch.setattr(dm.httpx, "AsyncClient", lambda **kw: _FakeMediaClient([], fail=True))

    await dm._run_direction_image_cleanup(_settings(), None)

    assert dm._job.status == "failed" and "media down" in dm._job.error
    assert log == []  # media-service never confirmed the delete, so no event was detached
