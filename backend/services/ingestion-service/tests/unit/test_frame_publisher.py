import numpy as np
import pytest

from app.streaming.frame_publisher import FramePublisher


class FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def xadd(self, stream_key: str, fields: dict, *, maxlen: int, approximate: bool) -> str:
        self.calls.append((stream_key, fields))
        return "0-1"


def _frame() -> np.ndarray:
    return np.zeros((4, 4, 3), dtype=np.uint8)


@pytest.mark.asyncio
async def test_publish_default_modality_uses_existing_stream_key() -> None:
    """Every existing (single-stream) camera never passes `modality` --
    stream key/behavior must be byte-for-byte what it was before M11."""
    redis_client = FakeRedis()
    publisher = FramePublisher(redis_client, jpeg_quality=80, maxlen=100)

    await publisher.publish("CAM-01", _frame(), loop_generation=0)

    stream_key, fields = redis_client.calls[0]
    assert stream_key == "cam:CAM-01:frames"
    assert fields["cameraId"] == "CAM-01"


@pytest.mark.asyncio
async def test_publish_with_modality_uses_a_separate_stream_but_the_same_camera_id() -> None:
    """M11: a 'dual' camera's thermal worker publishes to its own stream so
    it doesn't collide with the RGB stream -- but `cameraId` in the payload
    stays the real camera id, so detection-service's fusion step can still
    associate both streams' detections with the one logical camera."""
    redis_client = FakeRedis()
    publisher = FramePublisher(redis_client, jpeg_quality=80, maxlen=100)

    await publisher.publish("CAM-DUAL-01", _frame(), loop_generation=0, modality="thermal")

    stream_key, fields = redis_client.calls[0]
    assert stream_key == "cam:CAM-DUAL-01:frames:thermal"
    assert fields["cameraId"] == "CAM-DUAL-01"
