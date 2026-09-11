import numpy as np
import pytest

from app.schemas.pose import PoseReading
from app.services.pose_service import PoseService


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, list[PoseReading]]] = []

    async def publish(self, camera_id: str, poses: list[PoseReading]) -> None:
        self.published.append((camera_id, poses))


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


@pytest.mark.asyncio
async def test_process_frame_publishes_detected_readings() -> None:
    publisher = FakePublisher()
    readings = [PoseReading(x=10.0, y=20.0, posture="standing", confidence=0.9)]
    service = PoseService(publisher=publisher, detect=lambda frame: readings)

    result = await service.process_frame("CAM-01", _frame())

    assert result == readings
    assert publisher.published == [("CAM-01", readings)]


@pytest.mark.asyncio
async def test_process_frame_publishes_empty_list_when_nobody_detected() -> None:
    """Even a 'nobody in frame' result is published -- the frontend overlay
    needs the explicit empty update to clear a stale badge, the same
    reasoning `detection-service`'s own publisher gives for always
    refreshing `current_detections` even with zero detections."""
    publisher = FakePublisher()
    service = PoseService(publisher=publisher, detect=lambda frame: [])

    result = await service.process_frame("CAM-01", _frame())

    assert result == []
    assert publisher.published == [("CAM-01", [])]


@pytest.mark.asyncio
async def test_process_frame_reports_multiple_people() -> None:
    publisher = FakePublisher()
    readings = [
        PoseReading(x=10.0, y=20.0, posture="standing", confidence=0.9),
        PoseReading(x=60.0, y=40.0, posture="sitting", confidence=0.8),
        PoseReading(x=30.0, y=70.0, posture="sleeping", confidence=0.7),
    ]
    service = PoseService(publisher=publisher, detect=lambda frame: readings)

    result = await service.process_frame("CAM-02", _frame())

    assert len(result) == 3
    assert {r.posture for r in result} == {"standing", "sitting", "sleeping"}
