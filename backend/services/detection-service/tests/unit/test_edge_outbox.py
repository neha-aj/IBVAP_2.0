import json
import tempfile
from pathlib import Path

import pytest

from app.inference.edge_outbox import EdgeOutbox, EdgeOutboxPublisher
from app.schemas.detection import BoundingBox, Detection


@pytest.fixture
def outbox(tmp_path: Path) -> EdgeOutbox:
    return EdgeOutbox(str(tmp_path / "edge_outbox.db"))


def _detection(id: str = "d1") -> Detection:
    return Detection(id=id, camera_id="CAM-01", type="person", confidence=0.9, bbox=BoundingBox(x=1, y=1, width=1, height=1))


@pytest.mark.asyncio
async def test_enqueue_then_dequeue_roundtrip(outbox: EdgeOutbox) -> None:
    await outbox.enqueue(camera_id="CAM-01", detections_json="[]", loop_generation=0)

    batch = await outbox.dequeue_batch(10)

    assert len(batch) == 1
    assert batch[0]["camera_id"] == "CAM-01"


@pytest.mark.asyncio
async def test_dequeue_only_returns_unsynced_rows(outbox: EdgeOutbox) -> None:
    entry_id = await outbox.enqueue(camera_id="CAM-01", detections_json="[]")
    await outbox.mark_synced([entry_id])

    batch = await outbox.dequeue_batch(10)

    assert batch == []


@pytest.mark.asyncio
async def test_count_pending_and_synced(outbox: EdgeOutbox) -> None:
    id1 = await outbox.enqueue(camera_id="CAM-01", detections_json="[]")
    await outbox.enqueue(camera_id="CAM-01", detections_json="[]")

    assert await outbox.count_pending() == 2
    assert await outbox.count_synced() == 0

    await outbox.mark_synced([id1])

    assert await outbox.count_pending() == 1
    assert await outbox.count_synced() == 1


@pytest.mark.asyncio
async def test_dequeue_respects_limit_and_fifo_order(outbox: EdgeOutbox) -> None:
    for i in range(5):
        await outbox.enqueue(camera_id=f"CAM-{i}", detections_json="[]")

    batch = await outbox.dequeue_batch(2)

    assert len(batch) == 2
    assert batch[0]["camera_id"] == "CAM-0"
    assert batch[1]["camera_id"] == "CAM-1"


@pytest.mark.asyncio
async def test_outbox_survives_reopen_against_the_same_file(tmp_path: Path) -> None:
    """The whole point of a durable outbox -- data must survive the
    process (not just the connection) restarting."""
    db_path = str(tmp_path / "edge_outbox.db")
    first = EdgeOutbox(db_path)
    await first.enqueue(camera_id="CAM-01", detections_json="[]")

    second = EdgeOutbox(db_path)
    assert await second.count_pending() == 1


@pytest.mark.asyncio
async def test_local_alert_dedup_by_idempotency_key(outbox: EdgeOutbox) -> None:
    first = await outbox.record_local_alert(
        idempotency_key="CAM-01:zone:z1:d1", camera_id="CAM-01",
        event_type="Restricted Zone Entry", description="x", severity="high",
    )
    second = await outbox.record_local_alert(
        idempotency_key="CAM-01:zone:z1:d1", camera_id="CAM-01",
        event_type="Restricted Zone Entry", description="x", severity="high",
    )

    assert first is True
    assert second is False  # exact same key -- no duplicate row
    assert await outbox.count_pending_local_alerts() == 1


@pytest.mark.asyncio
async def test_edge_outbox_publisher_enqueues_serialized_detections(outbox: EdgeOutbox) -> None:
    publisher = EdgeOutboxPublisher(outbox)

    await publisher.publish("CAM-01", [_detection()], loop_generation=2)

    batch = await outbox.dequeue_batch(10)
    assert len(batch) == 1
    assert batch[0]["loop_generation"] == 2
    stored = json.loads(batch[0]["detections_json"])
    assert stored[0]["id"] == "d1"
