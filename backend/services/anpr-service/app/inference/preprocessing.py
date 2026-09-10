"""Crop/upscale/normalize a vehicle detection's bbox region out of a full
frame, per doc09 §2.1's preprocessing steps. Pure numpy/OpenCV array
transforms -- no model, no I/O."""

from __future__ import annotations

import cv2
import numpy as np


def crop_bbox_percent(frame: np.ndarray, *, x: float, y: float, width: float, height: float) -> np.ndarray:
    """`x`/`y`/`width`/`height` are percent-of-frame (0-100), the same units
    every detection bbox in this codebase already uses."""
    frame_h, frame_w = frame.shape[:2]
    x1 = max(0, min(frame_w, round(x / 100 * frame_w)))
    y1 = max(0, min(frame_h, round(y / 100 * frame_h)))
    x2 = max(0, min(frame_w, round((x + width) / 100 * frame_w)))
    y2 = max(0, min(frame_h, round((y + height) / 100 * frame_h)))
    if x2 <= x1 or y2 <= y1:
        return frame[0:0, 0:0]  # empty crop -- caller checks .size before use
    return frame[y1:y2, x1:x2]


def upscale_if_small(crop: np.ndarray, *, min_height_px: int) -> np.ndarray:
    """doc09 §2.1: "upscale if crop height <64px" -- a distant/small plate
    crop otherwise gives the OCR engine too few pixels per character."""
    if crop.size == 0:
        return crop
    height, width = crop.shape[:2]
    if height >= min_height_px:
        return crop
    scale = min_height_px / height
    return cv2.resize(crop, (max(1, int(width * scale)), min_height_px), interpolation=cv2.INTER_CUBIC)


def normalize_for_ocr(crop: np.ndarray) -> np.ndarray:
    """doc09 §2.1: "grayscale + contrast normalization before OCR"."""
    if crop.size == 0:
        return crop
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return cv2.equalizeHist(gray)
