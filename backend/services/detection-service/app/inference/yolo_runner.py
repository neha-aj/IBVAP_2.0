"""Primary inference backend: Ultralytics YOLOv8, torch-backed. Ultralytics
picks CUDA automatically when available and falls back to CPU otherwise, so
this single runner covers both the GPU and default-CPU deployment cases
(SAS §5.2, §9 GPU services)."""

from __future__ import annotations

import numpy as np

from app.inference.base import COCO_TYPE_MAP, RawDetection


class YoloRunner:
    def __init__(self, *, model_path: str, confidence_threshold: float) -> None:
        from ultralytics import YOLO  # deferred: heavy import, torch init

        self._model = YOLO(model_path)
        self._confidence_threshold = confidence_threshold

    def infer(self, frame: np.ndarray) -> list[RawDetection]:
        results = self._model.predict(
            frame,
            conf=self._confidence_threshold,
            classes=list(COCO_TYPE_MAP.keys()),
            # `COCO_TYPE_MAP` deliberately coalesces several raw COCO classes
            # into one reported type each (car/motorcycle/bus/truck ->
            # "vehicle"; 8 species -> "animal"). Ultralytics' NMS is
            # per-class by default, so one real object YOLO scores
            # ambiguously between two of those raw classes (e.g. a
            # car-or-truck-shaped SUV) can survive as two separate
            # overlapping boxes -- confirmed live: a single parked SUV
            # produced 2-3 simultaneous "vehicle" boxes/track ids on one of
            # this deployment's real camera feeds. `agnostic_nms=True`
            # suppresses overlapping boxes across all classes together,
            # matching `OnnxRunner`'s NMS below (which is already
            # class-agnostic, since `cv2.dnn.NMSBoxes` there is never given
            # per-class grouping) -- this brings the two backends' behavior
            # in line with each other, not a new tradeoff unique to one.
            agnostic_nms=True,
            verbose=False,
        )
        detections: list[RawDetection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box, confidence, class_id in zip(
                boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), strict=False
            ):
                x1, y1, x2, y2 = box
                detections.append(
                    RawDetection(
                        class_id=int(class_id),
                        confidence=float(confidence),
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                    )
                )
        return detections
