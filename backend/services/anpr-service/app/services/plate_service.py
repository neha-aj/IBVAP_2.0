"""Orchestrates one vehicle detection through the full ANPR pipeline (doc09
§2.1): fetch current frame -> crop -> preprocess -> localize plate -> OCR ->
validate format -> check watchlist -> persist -> store crop -> report.

`detect_plate`/`read_plate` are injected callables (not hardcoded to
`PlateDetector.detect`/`ocr.read_plate_text`) specifically so this
orchestration logic is unit-testable without a real Haar cascade or the
Tesseract binary -- main.py wires the real implementations at startup.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import cv2
import numpy as np

from ibvap_common.logging import get_logger

from app.core.config import Settings
from app.inference import ocr, preprocessing
from app.models.plate_read import PlateRead
from app.repositories.plate_read_repo import PlateReadRepository
from app.repositories.watchlist_repo import WatchlistRepository
from app.schemas.internal import Detection
from app.streaming.camera_client import CameraClient
from app.streaming.event_client import EventClient
from app.streaming.media_client import MediaClient

logger = get_logger(__name__)

DetectPlateFn = Callable[[np.ndarray], tuple[int, int, int, int] | None]
ReadPlateFn = Callable[[np.ndarray], tuple[str, float] | None]


class PlateService:
    def __init__(
        self,
        *,
        settings: Settings,
        plate_repo: PlateReadRepository,
        watchlist_repo: WatchlistRepository,
        camera_client: CameraClient,
        media_client: MediaClient,
        event_client: EventClient,
        detect_plate: DetectPlateFn,
        read_plate: ReadPlateFn,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._plate_repo = plate_repo
        self._watchlist_repo = watchlist_repo
        self._camera_client = camera_client
        self._media_client = media_client
        self._event_client = event_client
        self._detect_plate = detect_plate
        self._read_plate = read_plate
        self._now = now
        # (camera_id, plate_text) -> last time this exact plate was
        # persisted on this camera (see Settings.plate_read_cooldown_seconds
        # for why this exists instead of a per-track dedup).
        self._last_persisted_at: dict[tuple[str, str], float] = {}

    async def process_vehicle_detection(self, detection: Detection) -> PlateRead | None:
        if detection.type != "vehicle":
            return None

        frame_bytes = await self._camera_client.get_current_frame(detection.cameraId)
        if frame_bytes is None:
            return None
        frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None

        crop = preprocessing.crop_bbox_percent(
            frame, x=detection.bbox.x, y=detection.bbox.y,
            width=detection.bbox.width, height=detection.bbox.height,
        )
        if crop.size == 0:
            return None
        crop = preprocessing.upscale_if_small(crop, min_height_px=self._settings.min_plate_crop_height_px)
        gray = preprocessing.normalize_for_ocr(crop)

        plate_region = self._detect_plate(gray)
        if plate_region is None:
            return None
        x, y, w, h = plate_region
        plate_gray = gray[y : y + h, x : x + w]

        result = self._read_plate(plate_gray)
        if result is None:
            return None
        plate_text, confidence = result
        if not ocr.is_valid_plate_format(plate_text, self._settings.plate_format_regex):
            return None

        cooldown_key = (detection.cameraId, plate_text)
        last_persisted = self._last_persisted_at.get(cooldown_key)
        now = self._now()
        if last_persisted is not None and now - last_persisted < self._settings.plate_read_cooldown_seconds:
            return None  # same plate, same camera, still within the window -- already recorded recently
        self._last_persisted_at[cooldown_key] = now

        watchlist_entry = await self._watchlist_repo.get_by_plate(plate_text)
        watchlist_match = watchlist_entry is not None

        snapshot_id = None
        encoded_ok, encoded = cv2.imencode(".jpg", plate_gray)
        if encoded_ok:
            stored = await self._media_client.store_plate_crop(
                camera_id=detection.cameraId, jpeg_bytes=encoded.tobytes()
            )
            if stored is not None:
                snapshot_id = stored.id

        plate_read = await self._plate_repo.create(
            PlateRead(
                camera_id=detection.cameraId,
                track_id=detection.trackId,
                plate_text=plate_text,
                confidence=confidence,
                snapshot_id=snapshot_id,
                watchlist_match=watchlist_match,
            )
        )

        await self._event_client.report_plate_read(
            camera_id=detection.cameraId, plate_text=plate_text, confidence=confidence,
            watchlist_match=watchlist_match,
        )
        logger.info(
            "plate_read_processed", camera_id=detection.cameraId, plate_text=plate_text,
            watchlist_match=watchlist_match,
        )
        return plate_read
