"""Covers (1) the fusion merge no longer double-counting an object both
modalities saw, (2) FrameConsumer's derived-thermal path (detect on the
simulated thermal rendering of the same frame, fuse, publish once), and (3)
FrameConsumer skipping frames of a paused camera."""

import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.inference.base import RawDetection
from app.inference.fusion_merger import FusionSettings, merge_detections
from app.schemas.detection import BoundingBox, Detection
from app.streaming.consumer_manager import ConsumerManager
from app.streaming.frame_consumer import FrameConsumer


def _det(*, type: str = "person", confidence: float = 0.8, x: float = 10.0, y: float = 10.0,
         w: float = 10.0, h: float = 20.0, id: str = "d") -> Detection:
    return Detection(id=id, camera_id="CAM", type=type, confidence=confidence,
                     bbox=BoundingBox(x=x, y=y, width=w, height=h))


# --- fusion: no double counting ------------------------------------------

def test_confident_rgb_person_and_its_thermal_twin_count_once() -> None:
    """The bug: a confident RGB detection skipped the thermal lookup, and the
    same person's thermal detection was then appended as 'thermal-only' too."""
    rgb = [_det(id="rgb", confidence=0.9)]
    thermal = [_det(id="thermal", confidence=0.85)]

    merged = merge_detections(rgb, thermal, FusionSettings())

    assert [d.id for d in merged] == ["rgb"]


def test_several_people_each_counted_once_across_both_views() -> None:
    rgb = [_det(id="r1", x=5), _det(id="r2", x=40), _det(id="r3", x=70)]
    thermal = [_det(id="t1", x=5.5), _det(id="t2", x=40.5), _det(id="t3", x=69.5)]

    merged = merge_detections(rgb, thermal, FusionSettings())

    assert len(merged) == 3
    assert {d.id for d in merged} == {"r1", "r2", "r3"}


def test_a_genuinely_different_thermal_only_object_is_still_kept() -> None:
    rgb = [_det(id="rgb", x=5)]
    thermal = [_det(id="t-same", x=5.5), _det(id="t-other", x=70)]

    merged = merge_detections(rgb, thermal, FusionSettings())

    assert {d.id for d in merged} == {"rgb", "t-other"}


def test_overlapping_thermal_box_of_a_different_type_is_not_absorbed() -> None:
    """A person riding a bike overlaps the bike's box -- different types are
    different objects and both must survive."""
    rgb = [_det(id="bike", type="vehicle", confidence=0.9, x=10, y=10, w=12, h=20)]
    thermal = [_det(id="rider", type="person", confidence=0.9, x=11, y=10, w=10, h=18)]

    merged = merge_detections(rgb, thermal, FusionSettings())

    assert {d.id for d in merged} == {"bike", "rider"}


def test_low_confidence_thermal_only_object_dropped_when_a_floor_is_set() -> None:
    thermal = [_det(id="weak", confidence=0.40), _det(id="strong", x=60, confidence=0.7)]

    merged = merge_detections([], thermal, FusionSettings(thermal_only_min_confidence=0.5))

    assert [d.id for d in merged] == ["strong"]


def test_default_settings_still_pass_every_thermal_only_object_through() -> None:
    thermal = [_det(id="weak", confidence=0.40)]

    assert [d.id for d in merge_detections([], thermal, FusionSettings())] == ["weak"]


def test_a_larger_thermal_box_around_the_rgb_person_is_the_same_person() -> None:
    """A thermal blob often includes a floor reflection or warm trail, so its box is
    much bigger than the RGB one: low IoU, but it plainly contains the person."""
    rgb = [_det(id="rgb", x=40, y=30, w=10, h=30)]
    thermal = [_det(id="blob", confidence=0.8, x=38, y=28, w=16, h=52)]  # taller and wider: reflection included

    merged = merge_detections(rgb, thermal, FusionSettings())

    assert [d.id for d in merged] == ["rgb"]


def test_a_smaller_thermal_box_inside_the_rgb_box_is_the_same_person() -> None:
    rgb = [_det(id="rgb", x=30, y=20, w=20, h=50)]
    thermal = [_det(id="head", confidence=0.8, x=34, y=22, w=8, h=14)]

    assert [d.id for d in merge_detections(rgb, thermal, FusionSettings())] == ["rgb"]


def test_two_people_standing_side_by_side_are_still_two_people() -> None:
    rgb = [_det(id="left", x=20, y=20, w=12, h=40)]
    thermal = [_det(id="right", confidence=0.8, x=31, y=20, w=12, h=40)]  # only their edges touch

    assert {d.id for d in merge_detections(rgb, thermal, FusionSettings())} == {"left", "right"}


def test_containment_only_merges_boxes_of_the_same_type() -> None:
    rgb = [_det(id="car", type="vehicle", confidence=0.9, x=10, y=20, w=40, h=25)]
    thermal = [_det(id="driver", type="person", confidence=0.8, x=20, y=25, w=8, h=15)]  # inside the car's box

    assert {d.id for d in merge_detections(rgb, thermal, FusionSettings())} == {"car", "driver"}


# --- FrameConsumer -------------------------------------------------------

class _FakeRedis:
    def __init__(self, paused: set[str] | None = None) -> None:
        self.paused = paused or set()
        self.acked: list[bytes] = []

    async def sismember(self, key: str, member: str) -> bool:
        return member in self.paused

    async def xack(self, stream_key, group, message_id) -> None:
        self.acked.append(message_id)


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[list[Detection]] = []

    async def publish(self, camera_id: str, detections: list[Detection], *, loop_generation: int = 0) -> None:
        self.calls.append(detections)


class _TwoViewEngine:
    """Sees the same person in both views (RGB and simulated thermal)."""

    def __init__(self) -> None:
        self.infer_calls = 0

    def infer(self, frame: np.ndarray) -> list[RawDetection]:
        self.infer_calls += 1
        return [RawDetection(class_id=0, confidence=0.9, x1=100, y1=50, x2=180, y2=250)]


def _message(*, derived: bool) -> dict[bytes, bytes]:
    frame = np.full((400, 400, 3), 90, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    fields = {b"jpeg": encoded.tobytes(), b"loopGeneration": b"0"}
    if derived:
        fields[b"derivedThermal"] = b"1"
    return fields


def _consumer(redis, engine, publisher, *, fusion: FusionSettings | None) -> FrameConsumer:
    return FrameConsumer(
        camera_id="CAM", redis_client=redis, engine=engine, publisher=publisher,
        group_name="g", read_count=5, block_ms=10, derived_thermal_fusion=fusion,
    )


@pytest.mark.asyncio
async def test_derived_thermal_frame_is_analysed_in_both_views_but_counted_once() -> None:
    redis, engine, publisher = _FakeRedis(), _TwoViewEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings(thermal_only_min_confidence=0.5))

    await consumer._process_message(b"1-0", _message(derived=True))

    assert engine.infer_calls == 2  # RGB view + simulated thermal view
    assert len(publisher.calls) == 1
    assert len(publisher.calls[0]) == 1  # the one person, not two
    assert redis.acked == [b"1-0"]


@pytest.mark.asyncio
async def test_ordinary_frame_is_analysed_once_exactly_as_before() -> None:
    redis, engine, publisher = _FakeRedis(), _TwoViewEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings())

    await consumer._process_message(b"1-0", _message(derived=False))

    assert engine.infer_calls == 1
    assert len(publisher.calls[0]) == 1


@pytest.mark.asyncio
async def test_paused_camera_frame_is_skipped_without_inference_but_still_acked() -> None:
    redis, engine, publisher = _FakeRedis(paused={"CAM"}), _TwoViewEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings())

    await consumer._process_message(b"7-0", _message(derived=True))

    assert engine.infer_calls == 0
    assert publisher.calls == []
    assert redis.acked == [b"7-0"]  # not left pending forever


class _PausesDuringInference(_TwoViewEngine):
    """Simulates the operator pausing while a slow inference is in flight."""

    def __init__(self, redis: "_FakeRedis") -> None:
        super().__init__()
        self._redis = redis

    def infer(self, frame: np.ndarray) -> list[RawDetection]:
        result = super().infer(frame)
        self._redis.paused.add("CAM")
        return result


@pytest.mark.asyncio
async def test_result_of_a_frame_paused_mid_inference_is_dropped_not_published() -> None:
    redis = _FakeRedis()
    publisher = _RecordingPublisher()
    consumer = _consumer(redis, _PausesDuringInference(redis), publisher, fusion=FusionSettings())

    await consumer._process_message(b"3-0", _message(derived=False))

    assert publisher.calls == []
    assert redis.acked == [b"3-0"]


@pytest.mark.asyncio
async def test_a_different_paused_camera_does_not_stop_this_one() -> None:
    redis, engine, publisher = _FakeRedis(paused={"OTHER"}), _TwoViewEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings())

    await consumer._process_message(b"1-0", _message(derived=False))

    assert engine.infer_calls == 1


# --- ConsumerManager -----------------------------------------------------

def _settings(**overrides) -> Settings:
    defaults = {"postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
                "internal_service_token": "t"}
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_generated_thermal_dual_camera_gets_a_single_consumer() -> None:
    from unittest.mock import AsyncMock

    manager = ConsumerManager(_settings(), engine=object())
    manager._fetch_camera_configs = AsyncMock(return_value=[
        {"id": "CAM-D", "type": "dual", "thermalSourceUrl": "derived:rgb"},
    ])
    started: list[str] = []
    manager._start_consumer = lambda **kw: started.append(kw["consumer_key"])  # type: ignore[method-assign]

    await manager._reconcile()

    assert started == ["CAM-D"]  # one consumer, on the RGB stream; no ':thermal' pair, no fusion merger


@pytest.mark.asyncio
async def test_real_dual_camera_still_gets_its_two_consumers() -> None:
    from unittest.mock import AsyncMock

    manager = ConsumerManager(_settings(), engine=object())
    manager._fetch_camera_configs = AsyncMock(return_value=[
        {"id": "CAM-D", "type": "dual", "thermalSourceUrl": "/uploads/thermal.mp4"},
    ])
    started: list[str] = []
    manager._start_consumer = lambda **kw: started.append(kw["consumer_key"])  # type: ignore[method-assign]

    await manager._reconcile()

    assert sorted(started) == ["CAM-D:rgb", "CAM-D:thermal"]


# --- the thermal image shipped by ingestion ------------------------------------

class _ShapeAwareEngine:
    """RGB frames (400x400) show nothing; the thermal image (100x200) shows one
    person on its right -- so a result only appears if the thermal image itself
    was analysed, and its x position reveals which image size it was scaled by."""

    def __init__(self) -> None:
        self.seen_shapes: list[tuple[int, int]] = []

    def infer(self, frame: np.ndarray) -> list[RawDetection]:
        self.seen_shapes.append(frame.shape[:2])
        if frame.shape[:2] == (100, 200):
            return [RawDetection(class_id=0, confidence=0.9, x1=140, y1=10, x2=190, y2=90)]
        return []


def _thermal_jpeg(height: int = 100, width: int = 200) -> bytes:
    ok, encoded = cv2.imencode(".jpg", np.full((height, width, 3), 60, dtype=np.uint8))
    assert ok
    return encoded.tobytes()


@pytest.mark.asyncio
async def test_the_thermal_image_from_ingestion_is_what_gets_analysed_at_its_own_size() -> None:
    redis, engine, publisher = _FakeRedis(), _ShapeAwareEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings(thermal_only_min_confidence=0.5))
    fields = _message(derived=True)
    fields[b"thermalJpeg"] = _thermal_jpeg()

    await consumer._process_message(b"1-0", fields)

    assert (100, 200) in engine.seen_shapes  # the shipped thermal image itself, not a re-render of the RGB frame
    assert len(publisher.calls[0]) == 1
    # 140/200 of the way across the *thermal* image; scaled by the RGB frame's width it'd be 35%.
    assert publisher.calls[0][0].bbox.x == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_an_undecodable_thermal_image_falls_back_to_rendering_from_the_frame() -> None:
    redis, engine, publisher = _FakeRedis(), _ShapeAwareEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings())
    fields = _message(derived=True)
    fields[b"thermalJpeg"] = b"this is not a jpeg"

    await consumer._process_message(b"1-0", fields)

    assert engine.seen_shapes == [(400, 400), (400, 400)]  # RGB, then the fallback rendering of it (same size)
    assert redis.acked == [b"1-0"]  # the frame was still processed, not dropped


@pytest.mark.asyncio
async def test_a_derived_frame_without_a_shipped_thermal_image_still_works() -> None:
    """Frames queued by an older ingestion (no `thermalJpeg`) must keep being analysed."""
    redis, engine, publisher = _FakeRedis(), _TwoViewEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings())

    await consumer._process_message(b"1-0", _message(derived=True))

    assert engine.infer_calls == 2
    assert len(publisher.calls) == 1


class _RecordingEngine:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []

    def infer(self, frame: np.ndarray) -> list[RawDetection]:
        self.frames.append(frame)
        return []


@pytest.mark.asyncio
async def test_the_thermal_view_is_analysed_as_white_hot_greyscale() -> None:
    redis, engine, publisher = _FakeRedis(), _RecordingEngine(), _RecordingPublisher()
    consumer = _consumer(redis, engine, publisher, fusion=FusionSettings())
    fields = _message(derived=True)
    fields[b"thermalJpeg"] = _thermal_jpeg()

    await consumer._process_message(b"1-0", fields)

    rgb_frame, thermal_view = engine.frames
    assert rgb_frame.shape[:2] == (400, 400)  # the RGB frame goes to the model untouched
    assert thermal_view.shape[:2] == (100, 200)
    assert (thermal_view[..., 0] == thermal_view[..., 1]).all()  # greyscale: what the model reads well
