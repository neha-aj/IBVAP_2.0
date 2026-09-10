"""Crop a track's bbox region out of a full frame. Duplicated from
anpr-service's own `crop_bbox_percent` rather than shared, per Implementation
Guide §3 ("no service imports another service's package") -- pure
numpy/OpenCV, no model, no I/O."""

from __future__ import annotations

import numpy as np


def crop_bbox_percent(frame: np.ndarray, *, x: float, y: float, width: float, height: float) -> np.ndarray:
    """`x`/`y`/`width`/`height` are percent-of-frame (0-100)."""
    frame_h, frame_w = frame.shape[:2]
    x1 = max(0, min(frame_w, round(x / 100 * frame_w)))
    y1 = max(0, min(frame_h, round(y / 100 * frame_h)))
    x2 = max(0, min(frame_w, round((x + width) / 100 * frame_w)))
    y2 = max(0, min(frame_h, round((y + height) / 100 * frame_h)))
    if x2 <= x1 or y2 <= y1:
        return frame[0:0, 0:0]
    return frame[y1:y2, x1:x2]
