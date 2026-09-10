"""CPU-only fallback backend: a YOLOv8-exported ONNX model run through
ONNX Runtime, no torch dependency (SAS §9: "a CPU-only ONNX Runtime fallback
image is provided for hosts without a GPU"). Selected by `model_registry`
when `settings.inference_backend == "onnx"` and the model file at
`onnx_model_path` exists.

Implements YOLOv8's raw output decoding (letterbox resize, per-class argmax
over the 80 COCO classes, NMS) since ONNX Runtime only returns the raw
tensor -- Ultralytics normally does this postprocessing itself.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.inference.base import COCO_TYPE_MAP, RawDetection

_NMS_IOU_THRESHOLD = 0.45


class OnnxRunner:
    def __init__(self, *, model_path: str, confidence_threshold: float, input_size: int = 640) -> None:
        import onnxruntime as ort  # deferred: optional dependency

        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name
        self._input_size = input_size
        self._confidence_threshold = confidence_threshold

    def _letterbox(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        h, w = frame.shape[:2]
        scale = self._input_size / max(h, w)
        resized = cv2.resize(frame, (int(w * scale), int(h * scale)))
        canvas = np.zeros((self._input_size, self._input_size, 3), dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        return canvas, scale

    def infer(self, frame: np.ndarray) -> list[RawDetection]:
        canvas, scale = self._letterbox(frame)
        blob = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)

        outputs = self._session.run(None, {self._input_name: blob})[0]
        # YOLOv8 ONNX export shape: (1, 4 + num_classes, num_anchors).
        predictions = outputs[0].transpose(1, 0)  # (num_anchors, 4 + num_classes)

        xywh_boxes: list[list[float]] = []
        confidences: list[float] = []
        class_ids: list[int] = []
        for row in predictions:
            class_scores = row[4:]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])
            if confidence < self._confidence_threshold or class_id not in COCO_TYPE_MAP:
                continue
            cx, cy, w, h = row[:4]
            xywh_boxes.append([float(cx - w / 2), float(cy - h / 2), float(w), float(h)])
            confidences.append(confidence)
            class_ids.append(class_id)

        if not xywh_boxes:
            return []

        keep = cv2.dnn.NMSBoxes(
            xywh_boxes, confidences, self._confidence_threshold, _NMS_IOU_THRESHOLD
        )
        detections: list[RawDetection] = []
        for i in np.array(keep).flatten():
            x, y, w, h = xywh_boxes[i]
            detections.append(
                RawDetection(
                    class_id=class_ids[i],
                    confidence=confidences[i],
                    x1=x / scale,
                    y1=y / scale,
                    x2=(x + w) / scale,
                    y2=(y + h) / scale,
                )
            )
        return detections
