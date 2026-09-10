"""Classical-CV PPE check on an already-cropped person region (doc09 §2.8,
doc11 §5). doc11 §5 documents exactly one fallback when no fine-tuned PPE
dataset/model exists for a deployment: "Generic person detector [already
upstream, in detection-service] + simple color-region heuristic for
high-vis vests only" -- explicitly *not* a helmet check (no classical
equivalent is documented for detecting helmet presence/absence the way a
saturated, near-solid vest color patch can be detected). This module
implements exactly that documented scope: high-vis vest coverage over the
crop's torso band, nothing more. `classify_ppe`'s returned list is
therefore always either `[]` or `["vest"]` -- structured as a list (not a
bool) so a future fine-tuned model swap-in (multiple missing classes) is a
drop-in replacement for this function, not a shape change everywhere it's
called.

Same honest-limitation posture as fire-smoke-service's heuristics.py: not
validated against a real adversarial dataset, tuned empirically against
this deployment's own camera feeds. A bright-colored non-vest garment
(an orange jacket, a yellow raincoat) will read as "vest present" --
acceptable for a compliance-trend tool (doc09 §2.8's own caveat), not a
per-incident disciplinary source of truth.
"""

from __future__ import annotations

import cv2
import numpy as np

# Percent-of-crop-height band a high-vis vest is expected to occupy --
# roughly shoulders-to-waist, avoiding the head (skin/hair/helmet colors)
# and legs (trousers, rarely hi-vis) so those don't dilute the coverage
# fraction.
_TORSO_BAND = (0.20, 0.85)

# High-visibility "safety orange" and "safety yellow/lime" hue ranges in
# OpenCV's HSV (H: 0-179). Both need reasonably high saturation/value to
# exclude dull, desaturated real-world oranges/yellows (skin tones, wood,
# dirt) that would otherwise false-positive.
_ORANGE_HUE = (4, 22)
_YELLOW_GREEN_HUE = (24, 95)
_MIN_SATURATION = 110
_MIN_VALUE = 110


def vest_coverage_fraction(crop: np.ndarray) -> float:
    """Fraction of the crop's torso band matching a high-vis vest color.
    Returns 0.0 for an empty/too-small crop rather than raising -- callers
    already guard crop size before classifying, but this stays safe to
    call standalone (e.g. from tests) without that guard."""
    if crop.size == 0:
        return 0.0

    height = crop.shape[0]
    y1 = int(height * _TORSO_BAND[0])
    y2 = int(height * _TORSO_BAND[1])
    band = crop[y1:y2]
    if band.size == 0:
        return 0.0

    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    is_orange = (h >= _ORANGE_HUE[0]) & (h <= _ORANGE_HUE[1])
    is_yellow_green = (h >= _YELLOW_GREEN_HUE[0]) & (h <= _YELLOW_GREEN_HUE[1])
    is_hi_vis_hue = is_orange | is_yellow_green
    is_saturated_and_bright = (s >= _MIN_SATURATION) & (v >= _MIN_VALUE)

    mask = is_hi_vis_hue & is_saturated_and_bright
    return float(mask.mean())


def classify_ppe(crop: np.ndarray, *, vest_min_coverage_fraction: float) -> list[str]:
    """Returns the list of required PPE classes judged absent -- `[]` if
    the vest check passes, `["vest"]` otherwise. See module docstring for
    why this never returns "helmet"."""
    if vest_coverage_fraction(crop) < vest_min_coverage_fraction:
        return ["vest"]
    return []
