"""Shared types for the inference backends (SAS §5.2: "Detection Service
consumes frames, runs YOLOv8 -- GPU if available, ONNX Runtime CPU
fallback"). Both `yolo_runner.YoloRunner` and `onnx_runner.OnnxRunner`
implement `InferenceEngine` so `model_registry.build_engine` can select
either one transparently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

# COCO class ids YOLOv8 is pretrained on, narrowed to the object types the
# rest of the pipeline understands -- everything else is dropped.
# Phase 2 M21 Animal Detection: doc11 §7 -- "enable existing COCO animal
# classes already present in the currently-deployed yolov8s.pt weights", no
# new model needed. Narrowed to COCO's common domestic/wildlife classes
# rather than all 10 COCO animal ids so a stray misclassification on an
# uncommon class doesn't produce a confusing "animal" label in practice;
# extend this set if a deployment needs a class not listed here.
COCO_TYPE_MAP: dict[int, str] = {
    0: "person",
    1: "vehicle",  # bicycle
    2: "vehicle",  # car
    3: "vehicle",  # motorcycle
    5: "vehicle",  # bus
    7: "vehicle",  # truck
    15: "animal",  # cat
    16: "animal",  # dog
    17: "animal",  # horse
    18: "animal",  # sheep
    19: "animal",  # cow
    20: "animal",  # elephant
    21: "animal",  # bear
    22: "animal",  # zebra
    23: "animal",  # giraffe
    # Abandoned Object Detection (behavioral analytics): the specific
    # "someone could leave this and walk away" COCO classes, not every
    # inanimate object YOLOv8 knows -- narrowed the same way the animal set
    # above is, so a stray misclassification on an unrelated class doesn't
    # produce a confusing "bag" label in practice.
    24: "bag",  # backpack
    26: "bag",  # handbag
    28: "bag",  # suitcase
}


@dataclass(frozen=True)
class RawDetection:
    """One raw detection in pixel coordinates, before percentage
    normalization (that's `streaming.detection_publisher`'s job)."""

    class_id: int
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class InferenceEngine(Protocol):
    """CPU-bound; callers run this via `asyncio.to_thread` (IG §3: "CPU-bound
    inference runs in a worker/process pool, never blocking the event loop")."""

    def infer(self, frame: np.ndarray) -> list[RawDetection]: ...
