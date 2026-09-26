"""Optional trained-model path for fire/smoke detection, alongside the
classical heuristics in heuristics.py. heuristics.py's own docstring is
explicit that it's a color/shape proxy *because no labeled fire/smoke
training data existed for this deployment* -- that's no longer true (see
models/README.md), so this exposes a real fine-tuned YOLOv8 model behind
the exact same `Callable[[np.ndarray], float]` signature
(fire_score/smoke_score) that FireSmokeService already expects, so it's a
drop-in replacement for the two injected callables, not a rewrite of
FireSmokeService itself. Blood detection has no equivalent trained model
(no labeled blood data existed in the training run either) and keeps using
heuristics.blood_score regardless of this flag.
"""

from __future__ import annotations

import numpy as np

from ibvap_common.logging import get_logger

logger = get_logger(__name__)

# D-Fire dataset class order, fixed at training time by the notebook that
# produced fire_smoke_best.pt -- not something discoverable from the
# weights file itself.
_FIRE_CLASS_ID = 0
_SMOKE_CLASS_ID = 1


class YoloFireSmokeScorer:
    """One instance shared across every camera's FireSmokeService (see
    reconcile_manager.py) -- loading the model itself is expensive, running
    it per frame is not, so it's created once, not per camera."""

    def __init__(self, *, model_path: str, confidence_threshold: float) -> None:
        from ultralytics import YOLO  # deferred: heavy import, torch init

        self._model = YOLO(model_path)
        self._confidence_threshold = confidence_threshold
        # fire_score/smoke_score are called back-to-back on the *same*
        # frame object by FireSmokeService.process_frame -- cached by
        # object identity so one frame only ever costs one inference call,
        # not two.
        self._cached_frame_id: int | None = None
        self._cached_confidences: dict[int, float] = {}

    def _confidences_for(self, frame: np.ndarray) -> dict[int, float]:
        if id(frame) == self._cached_frame_id:
            return self._cached_confidences

        results = self._model.predict(
            frame,
            conf=self._confidence_threshold,
            classes=[_FIRE_CLASS_ID, _SMOKE_CLASS_ID],
            verbose=False,
        )
        confidences: dict[int, float] = {}
        boxes = results[0].boxes
        if boxes is not None:
            for class_id, confidence in zip(boxes.cls.tolist(), boxes.conf.tolist(), strict=False):
                class_id = int(class_id)
                confidences[class_id] = max(confidences.get(class_id, 0.0), confidence)

        self._cached_frame_id = id(frame)
        self._cached_confidences = confidences
        return confidences

    def fire_score(self, frame: np.ndarray) -> float:
        return self._confidences_for(frame).get(_FIRE_CLASS_ID, 0.0)

    def smoke_score(self, frame: np.ndarray) -> float:
        return self._confidences_for(frame).get(_SMOKE_CLASS_ID, 0.0)


def load_if_enabled(*, model_path: str, confidence_threshold: float) -> YoloFireSmokeScorer | None:
    """Best-effort: a missing/corrupt weights file must not stop the
    service from starting -- it just means every camera falls back to the
    classical heuristics, same as before this model existed."""
    try:
        scorer = YoloFireSmokeScorer(model_path=model_path, confidence_threshold=confidence_threshold)
        logger.info("fire_smoke_trained_model_loaded", model_path=model_path)
        return scorer
    except Exception as exc:  # noqa: BLE001 -- any load failure degrades to heuristics, never crashes startup
        logger.warning("fire_smoke_trained_model_load_failed", model_path=model_path, error=str(exc))
        return None
