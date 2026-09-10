"""Classical edge-density plate localizer -- doc11 §1's fallback entry is
literally "Haar-cascade / classical edge-density plate localizer", but only
the Haar-cascade half ever got built (`plate_detector.py`). That cascade
(`haarcascade_russian_plate_number.xml`, the only plate cascade OpenCV
ships) was trained on Russian plates' specific proportions/features and
has notably low recall on other plate styles -- verified live: a demo
video with non-Russian-style plates produced a real screenshot for only
one vehicle, every other vehicle's plate region simply wasn't found at all
(the cascade returning no candidate is silent, not an error).

This implements the other, region-agnostic half of that same sanctioned
fallback: a plate's characters produce a dense cluster of strong vertical
edges in a fairly small, wide rectangle (roughly 2:1 to 6:1 width:height)
somewhere in the vehicle crop -- true regardless of plate format/country,
unlike a shape cascade trained on one specific style. `PlateDetector.detect`
tries the Haar cascade first (fast, precise when it matches its training
distribution) and falls back to this when the cascade finds nothing,
rather than replacing it -- each catches cases the other misses.

Same honest-limitation posture as this project's other classical-CV
fallbacks (fire-smoke's heuristics.py, tamper's tamper_detector.py): not
validated against a real adversarial dataset, and a lot of background
clutter (grillework, brand badges, headlight trim) can share the same
edge-density signature as a plate -- downstream OCR + format-regex
validation (`ocr.is_valid_plate_format`) is what actually rejects a
wrong candidate region, this only proposes one.
"""

from __future__ import annotations

import cv2
import numpy as np


def detect_by_edge_density(
    gray_crop: np.ndarray,
    *,
    min_aspect_ratio: float = 2.0,
    max_aspect_ratio: float = 6.0,
    min_area_fraction: float = 0.01,
    max_area_fraction: float = 0.5,
) -> tuple[int, int, int, int] | None:
    """Returns (x, y, w, h) in `gray_crop`'s own pixel space for the largest
    candidate region matching a plate's typical edge-density/aspect-ratio
    signature, or None if nothing qualifies."""
    if gray_crop.size == 0:
        return None
    height, width = gray_crop.shape[:2]
    total_area = height * width
    if total_area == 0:
        return None

    # Vertical Sobel: a plate's characters are a dense run of strong
    # vertical edges, distinct from a car body's mostly-smooth horizontal
    # gradients -- Otsu picks the threshold automatically per-crop rather
    # than a single fixed value that would only suit one lighting condition.
    sobel_x = cv2.Sobel(gray_crop, cv2.CV_8U, 1, 0, ksize=3)
    _, thresh = cv2.threshold(sobel_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Wide, short kernel: merges a plate's individual character edges into
    # one solid blob while leaving tall/narrow unrelated edge clusters
    # (e.g. a headlight bezel) unmerged.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best: tuple[int, int, int, int] | None = None
    best_area = 0
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h == 0:
            continue
        aspect_ratio = w / h
        area_fraction = (w * h) / total_area
        if not (min_aspect_ratio <= aspect_ratio <= max_aspect_ratio):
            continue
        if not (min_area_fraction <= area_fraction <= max_area_fraction):
            continue
        area = w * h
        if area > best_area:
            best_area = area
            best = (int(x), int(y), int(w), int(h))
    return best
