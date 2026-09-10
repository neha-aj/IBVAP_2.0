"""Plate localization within a vehicle crop -- OpenCV's bundled Haar
cascade, not a fine-tuned YOLOv8-plate model (doc11 §1's "Primary"), because
no plate-detection training data/weights exist for this deployment. doc11
§1 explicitly lists "Haar-cascade / classical edge-density plate localizer"
as the sanctioned fallback for exactly this situation ("no GPU... viable
only as an offline/embedded fallback") -- this is that fallback, not an ad
hoc shortcut. Swapping in a real fine-tuned detector later only means
replacing this one class; nothing downstream (OCR, persistence, alerting)
needs to change.

`detect()` tries the cascade first, then falls back to
`edge_plate_detector.detect_by_edge_density` when it finds nothing.
Verified live: `haarcascade_russian_plate_number.xml` (the only plate
cascade OpenCV ships) missed every plate but one in a real demo video of
non-Russian-style plates -- the cascade's training distribution just
doesn't cover most real-world plate styles, and it fails silently (no
candidate, not an error) rather than something a stricter/looser parameter
alone can fix. The edge-density fallback is region-agnostic, so it covers
exactly the gap the cascade's narrow training leaves.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.inference.edge_plate_detector import detect_by_edge_density


class PlateDetector:
    def __init__(self, cascade_name: str) -> None:
        cascade_path = Path(cv2.data.haarcascades) / cascade_name
        self._cascade = cv2.CascadeClassifier(str(cascade_path))
        if self._cascade.empty():
            raise RuntimeError(f"Failed to load Haar cascade '{cascade_name}' from {cascade_path}")

    def detect(self, gray_crop: np.ndarray) -> tuple[int, int, int, int] | None:
        """Returns (x, y, w, h) in `gray_crop`'s own pixel space for the
        best candidate plate region, or None if neither strategy finds
        one."""
        if gray_crop.size == 0:
            return None
        # minNeighbors=3, not the OpenCV-sample-typical 4: this cascade
        # already has low recall on non-Russian plates (see module
        # docstring) -- a slightly more permissive threshold catches more
        # real plates, and a wrong candidate here is still caught
        # downstream by OCR + format-regex validation, not silently
        # trusted.
        regions = self._cascade.detectMultiScale(gray_crop, scaleFactor=1.1, minNeighbors=3, minSize=(40, 12))
        if len(regions) > 0:
            x, y, w, h = max(regions, key=lambda r: r[2] * r[3])
            return int(x), int(y), int(w), int(h)
        return detect_by_edge_density(gray_crop)
