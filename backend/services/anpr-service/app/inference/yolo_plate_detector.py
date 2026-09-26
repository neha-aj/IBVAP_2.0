"""Optional trained-model path for plate localization, alongside the Haar
cascade + edge-density fallback in plate_detector.py. plate_detector.py's
own docstring is explicit that fine-tuned weights didn't exist for this
deployment when it was written -- that's no longer true (see
models/README.md) -- and says outright that "swapping in a real fine-tuned
detector later only means replacing this one class; nothing downstream
(OCR, persistence, alerting) needs to change." This is that class.

Takes the *color* crop, not the grayscale one PlateDetector.detect takes --
the Roboflow dataset this model was fine-tuned on is color, so detection
accuracy is better run before plate_service.py's own grayscale-normalize
step, not after. The returned (x, y, w, h) box is in the same pixel space
either way (grayscale conversion doesn't change image dimensions), so
nothing downstream needs to know which detector produced it.
"""

from __future__ import annotations

import numpy as np

from ibvap_common.logging import get_logger

logger = get_logger(__name__)

# The Roboflow license-plate-recognition-rxg4e dataset this model was
# fine-tuned on (see the training notebook) is single-class.
_PLATE_CLASS_ID = 0


class YoloPlateDetector:
    def __init__(self, *, model_path: str, confidence_threshold: float) -> None:
        from ultralytics import YOLO  # deferred: heavy import, torch init

        self._model = YOLO(model_path)
        self._confidence_threshold = confidence_threshold

    def detect(self, bgr_crop: np.ndarray) -> tuple[int, int, int, int] | None:
        if bgr_crop.size == 0:
            return None
        results = self._model.predict(
            bgr_crop, conf=self._confidence_threshold, classes=[_PLATE_CLASS_ID], verbose=False,
        )
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None
        # Highest-confidence box, same "best single candidate" contract as
        # PlateDetector.detect's own cascade path.
        best_index = int(boxes.conf.argmax())
        x1, y1, x2, y2 = boxes.xyxy[best_index].tolist()
        return int(x1), int(y1), int(x2 - x1), int(y2 - y1)


def load_if_enabled(*, model_path: str, confidence_threshold: float) -> YoloPlateDetector | None:
    """Best-effort: a missing/corrupt weights file must not stop the
    service from starting -- it just means every camera falls back to the
    Haar-cascade/edge-density path, same as before this model existed."""
    try:
        detector = YoloPlateDetector(model_path=model_path, confidence_threshold=confidence_threshold)
        logger.info("anpr_trained_model_loaded", model_path=model_path)
        return detector
    except Exception as exc:  # noqa: BLE001 -- any load failure degrades to the cascade, never crashes startup
        logger.warning("anpr_trained_model_load_failed", model_path=model_path, error=str(exc))
        return None
