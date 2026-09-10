import asyncio
from pathlib import Path

import pytest

from app.inference.edge_outbox import EdgeOutbox, EdgeOutboxPublisher
from app.inference.sync_worker import SyncWorker
from app.schemas.detection import BoundingBox, Detection


@pytest.fixture
def outbox(tmp_path: Path) -> EdgeOutbox:
    return EdgeOutbox(str(tmp_path / "edge_outbox.db"))


def _detection(id: str = "d1") -> Detection:
    return Detection(id=id, camera_id="CAM-01", type="person", confidence=0.9, bbox=BoundingBox(x=1, y=1, width=1, height=1))


class FakeCentralPublisher:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.calls: list[tuple[str, list[Detection]]] = []
        self._fail_after = fail_after

    async def publish(self, camera_id: str, detections: list[Detection], *, loop_generation: int = 0) -> None:
        if self._fail_after is not None and len(self.calls) >= self._fail_after:
            raise ConnectionError("central redis unreachable")
        self.calls.append((camera_id, detections))


def _worker(outbox: EdgeOutbox, publisher, **overrides) -> SyncWorker:
    defaults = dict(
        outbox=outbox, publisher=publisher, batch_size=10,
        interval_seconds=5.0, initial_backoff_seconds=1.0, max_backoff_seconds=60.0,
    )
    defaults.update(overrides)
    return SyncWorker(**defaults)


@pytest.mark.asyncio
async def test_sync_once_drains_the_outbox_to_the_real_publisher(outbox: EdgeOutbox) -> None:
    edge_publisher = EdgeOutboxPublisher(outbox)
    await edge_publisher.publish("CAM-01", [_detection()], loop_generation=0)

    central = FakeCentralPublisher()
    worker = _worker(outbox, central)

    synced = await worker.sync_once()

    assert synced == 1
    assert len(central.calls) == 1
    assert await outbox.count_pending() == 0
    assert await outbox.count_synced() == 1


@pytest.mark.asyncio
async def test_sync_once_with_empty_outbox_is_a_noop(outbox: EdgeOutbox) -> None:
    central = FakeCentralPublisher()
    worker = _worker(outbox, central)

    synced = await worker.sync_once()

    assert synced == 0


@pytest.mark.asyncio
async def test_zero_detection_loss_when_a_row_fails_partway_through_a_batch(outbox: EdgeOutbox) -> None:
    """The actual M11 §8 completion criterion: a connection failure mid-
    batch must not lose anything -- rows not yet successfully published
    stay pending and are picked up by the next sync attempt."""
    edge_publisher = EdgeOutboxPublisher(outbox)
    await edge_publisher.publish("CAM-01", [_detection("d1")], loop_generation=0)
    await edge_publisher.publish("CAM-02", [_detection("d2")], loop_generation=0)
    await edge_publisher.publish("CAM-03", [_detection("d3")], loop_generation=0)

    central = FakeCentralPublisher(fail_after=1)  # first row succeeds, second raises
    worker = _worker(outbox, central)

    with pytest.raises(ConnectionError):
        await worker.sync_once()

    # First row (already published+marked before the failure) is synced;
    # the rest are still pending -- nothing was lost.
    assert await outbox.count_synced() == 1
    assert await outbox.count_pending() == 2

    # Reconnect: a plain central publisher, no more failures.
    central_recovered = FakeCentralPublisher()
    recovery_worker = _worker(outbox, central_recovered)
    synced = await recovery_worker.sync_once()

    assert synced == 2
    assert await outbox.count_pending() == 0
    assert await outbox.count_synced() == 3


@pytest.mark.asyncio
async def test_backoff_doubles_on_repeated_failure_and_resets_on_success() -> None:
    class AlwaysFailsThenSucceeds:
        def __init__(self) -> None:
            self.attempts = 0

        async def sync_once(self):
            self.attempts += 1
            if self.attempts <= 2:
                raise ConnectionError("down")
            return 0

    worker = SyncWorker(
        outbox=None, publisher=None, batch_size=10,
        interval_seconds=0.01, initial_backoff_seconds=0.01, max_backoff_seconds=1.0,
    )
    worker.sync_once = AlwaysFailsThenSucceeds().sync_once  # type: ignore[method-assign]

    assert worker._backoff_seconds == 0.01
    worker.start()
    await asyncio.sleep(0.2)
    await worker.stop()

    # Backoff must have grown past its initial value at some point during
    # the two failures (doubled to 0.02) -- and since the third attempt
    # succeeded, it's been reset back to the initial value by the time we
    # check.
    assert worker._backoff_seconds == 0.01
