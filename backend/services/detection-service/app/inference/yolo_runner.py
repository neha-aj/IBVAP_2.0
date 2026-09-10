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
