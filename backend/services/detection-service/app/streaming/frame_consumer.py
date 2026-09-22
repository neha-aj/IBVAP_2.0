"""One `FrameConsumer` per camera, run as an asyncio task. Reads
`cam:{id}:frames` via a Redis Streams consumer group (SAS §5.2, §11
at-least-once processing), decodes each JPEG frame, runs inference in a
worker thread (IG §3: CPU-bound work never blocks the event loop), and
publishes the normalized detections.
"""

from __future__ import annotations

import asyncio

import cv2
import numpy as np
import redis.asyncio as redis
from prometheus_client import Counter

from ibvap_common.camera_pause import PAUSED_CAMERAS_KEY
from ibvap_common.logging import correlation_id_context, get_logger
from ibvap_common.redis_streams import ensure_consumer_group, xack, xread_group
from ibvap_common.thermal_sim import simulate_thermal, to_detection_view

from app.inference.base import InferenceEngine
from app.inference.fusion_merger import FusionSettings, merge_detections
from app.streaming.detection_publisher import DetectionPublisher, to_detections

logger = get_logger(__name__)

_FRAMES_PROCESSED = Counter(
    "detection_frames_processed_total", "Frames run through inference", ["camera_id"]
)


class FrameConsumer:
    def __init__(
        self,
        *,
        camera_id: str,
        redis_client: redis.Redis,
        engine: InferenceEngine,
        publisher: DetectionPublisher,
        group_name: str,
        read_count: int,
        block_ms: int,
        modality: str | None = None,
        derived_thermal_fusion: FusionSettings | None = None,
    ) -> None:
        self.camera_id = camera_id
        self._redis = redis_client
        self._engine = engine
        self._publisher = publisher
        self._group_name = group_name
        self._read_count = read_count
        self._block_ms = block_ms
        # M11: None for every existing (single-stream) camera type --
        # `_stream_key` is exactly what it was before. A 'dual' camera's
        # second consumer passes modality="thermal" to read the parallel
        # stream Stream Ingestion's second capture worker writes to
        # (`FramePublisher.publish`'s own `modality` param, same naming).
        # `self.camera_id` is deliberately left as the real camera id either
        # way -- only the stream key changes, so publishing/logging/consumer
        # naming below stay associated with the actual camera.
        self._stream_key = f"cam:{camera_id}:frames" if modality is None else f"cam:{camera_id}:frames:{modality}"
        # Only used for a camera whose thermal view is *derived* from its own
        # RGB video: ingestion flags each such frame (`derivedThermal`), and
        # this consumer then also detects on the simulated thermal rendering
        # of the same frame and fuses the two into one result (see
        # `_detect_with_derived_thermal`). None/no flag = every other camera,
        # unchanged.
        self._derived_thermal_fusion = derived_thermal_fusion
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name=f"frame-consumer-{self.camera_id}")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        await ensure_consumer_group(self._redis, self._stream_key, self._group_name)
        consumer_name = f"consumer-{self.camera_id}"

        while not self._stop_requested:
            try:
                messages = await xread_group(
                    self._redis,
                    group_name=self._group_name,
                    consumer_name=consumer_name,
                    stream_key=self._stream_key,
                    count=self._read_count,
                    block_ms=self._block_ms,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("frame_read_failed", camera_id=self.camera_id, error=str(exc))
                await asyncio.sleep(1.0)
                continue

            for message_id, fields in messages:
                await self._process_message(message_id, fields)

    async def _process_message(self, message_id: bytes, fields: dict[bytes, bytes]) -> None:
        correlation_id = (fields.get(b"correlationId") or b"").decode()
        with correlation_id_context(correlation_id):
            try:
                # A paused camera must produce no further detections. Ingestion
                # already stops feeding it and clears the queue, but this
                # consumer reads a batch ahead -- frames it had already pulled
                # when the pause landed would otherwise still be run through
                # inference (seconds of it, on CPU), and the counts on screen
                # would keep shifting after the operator froze the view.
                if await self._is_paused():
                    return
                jpeg_bytes = fields.get(b"jpeg")
                if jpeg_bytes:
                    loop_generation = int(fields.get(b"loopGeneration", b"0") or b"0")
                    frame = await asyncio.to_thread(_decode_jpeg, jpeg_bytes)
                    if frame is not None:
                        height, width = frame.shape[:2]
                        raw_detections = await asyncio.to_thread(self._engine.infer, frame)
                        detections = to_detections(
                            camera_id=self.camera_id,
                            raw_detections=raw_detections,
                            frame_width=width,
                            frame_height=height,
                        )
                        if fields.get(b"derivedThermal") and self._derived_thermal_fusion is not None:
                            detections = await self._detect_with_derived_thermal(
                                frame, detections, thermal_jpeg=fields.get(b"thermalJpeg")
                            )
                        # Inference on CPU can take seconds; if the operator paused
                        # meanwhile, this frame's result is stale by the time it's
                        # ready -- drop it rather than publish after the freeze.
                        if await self._is_paused():
                            return
                        await self._publisher.publish(self.camera_id, detections, loop_generation=loop_generation)
                        _FRAMES_PROCESSED.labels(camera_id=self.camera_id).inc()
            except Exception as exc:
                logger.warning(
                    "frame_inference_failed", camera_id=self.camera_id, error=str(exc)
                )
            finally:
                # Ack even on failure -- a single malformed/undecodable frame
                # should never block the stream forever (SAS §11: degrade
                # gracefully rather than crash or stall).
                await xack(self._redis, self._stream_key, self._group_name, message_id)

    async def _is_paused(self) -> bool:
        try:
            return bool(await self._redis.sismember(PAUSED_CAMERAS_KEY, self.camera_id))
        except Exception as exc:  # noqa: BLE001 -- a Redis blip must not stall inference
            logger.warning("pause_state_check_failed", camera_id=self.camera_id, error=str(exc))
            return False

    async def _detect_with_derived_thermal(
        self, frame: np.ndarray, rgb_detections: list, *, thermal_jpeg: bytes | None
    ) -> list:
        """Runs detection on the simulated thermal rendering of this same
        frame and fuses it with the RGB result. Both views show the same
        objects in the same places, so the fusion merge treats matching boxes
        as one object (never two) -- a person is counted once no matter how
        many of the two views saw them."""
        # Ingestion renders the thermal view (it tracks motion over time, which a single
        # frame can't) and ships it with the frame; a frame without one falls back to the
        # stateless ambient-only rendering.
        thermal_frame = await asyncio.to_thread(_decode_jpeg, thermal_jpeg) if thermal_jpeg else None
        if thermal_frame is None:
            thermal_frame = await asyncio.to_thread(simulate_thermal, frame)
        # The thermal image can be a different size from the RGB frame (it's capped in width),
        # and boxes are percentages of their own image.
        thermal_height, thermal_width = thermal_frame.shape[:2]
        # Detected on as white-hot greyscale: the same heat data, in a form the model can read.
        raw_thermal = await asyncio.to_thread(lambda: self._engine.infer(to_detection_view(thermal_frame)))
        thermal_detections = to_detections(
            camera_id=self.camera_id, raw_detections=raw_thermal,
            frame_width=thermal_width, frame_height=thermal_height,
        )
        return merge_detections(rgb_detections, thermal_detections, self._derived_thermal_fusion)


def _decode_jpeg(jpeg_bytes: bytes) -> np.ndarray | None:
    array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)
