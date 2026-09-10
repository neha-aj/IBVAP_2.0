"""Fire/smoke detection -- classical color-and-shape heuristics, NOT a
trained model. doc11 §4's primary recommendation is a fine-tuned YOLOv8 on
fire/smoke-labeled data (e.g. D-Fire); its documented fallback is "a
pretrained generic fire-detection model as a starting checkpoint." Neither
exists for this deployment -- and unlike Person/Vehicle Re-ID (M16/M17),
there's no generic pretrained classifier (ImageNet-style) whose features
happen to transfer to "is this fire," because fire/smoke detection is a
genuine appearance-classification task, not a similarity/retrieval one.

So this uses real, standard, pre-deep-learning fire-detection techniques
instead:

- Fire: the widely-cited rule-based approach of an HSV color-range test
  (warm hue, high saturation/value) combined with an RGB-ordering test
  (R > G > B, R above a brightness floor) -- e.g. Chen et al.'s rule-based
  fire-pixel classification, a standard pre-CNN baseline in the fire-
  detection literature, not something invented for this codebase.
- Smoke: low-saturation, mid-brightness ("greyish, hazy") region test --
  a common simplified color heuristic for smoke; real smoke detectors
  typically also use temporal/motion features (smoke is semi-transparent
  and drifts) which this deliberately omits for simplicity -- a real
  accuracy limitation, not a hidden shortcut.

**Both heuristics are colour/brightness proxies, not fire/smoke
classifiers.** doc09 §2.6 explicitly names the exact failure modes to
expect: sunset footage and orange/warm artificial lighting will trigger
the fire heuristic; steam, fog, and dust will trigger the smoke heuristic.
This is real, working code that does what it claims (detects
warm-colored / hazy-grey regions), but it is *not* validated against a
labeled fire/smoke benchmark -- there is no such dataset available in this
deployment to validate against. Treat any alert this produces as an
early-warning aid requiring human confirmation, per doc09 §2.6's own
framing, not a validated fire-detection result. Replacing this module with
a real trained detector is a drop-in swap (same `(frame) -> float` shape)
whenever labeled data/weights become available.

**Live-tested against this deployment's 3 real camera feeds and tuned
against two real false positives found that way** (not a substitute for
the adversarial-dataset validation doc09 §2.6 calls for, which needs
labeled fire/smoke footage this deployment doesn't have -- but real,
not skipped):
1. A plain sandy/paved ground area read as "smoke" (uniform, low-
   saturation, moderate brightness -- exactly what the color test alone
   looks for). Fixed by also requiring *low local texture* (Laplacian-
   edge-magnitude, blurred) within the candidate region -- real haze
   suppresses fine detail the way a flat sandy/paved surface's visible
   grain/cracks/footprints don't.
2. An overcast sky read as "smoke" for the same color reason, and it
   passes the texture test too (sky genuinely has near-zero local
   texture). Fixed by excluding a configurable top-of-frame band from
   smoke candidacy (`Settings.smoke_sky_exclude_fraction`) -- a real
   tradeoff, not a free fix: it would also suppress a genuine smoke
   plume that only ever appears high in frame (e.g. a distant rooftop
   fire). Reasonable for this deployment's roughly-horizontal perimeter
   cameras, where the excluded band is normally sky, not scene content.
"""

from __future__ import annotations

import cv2
import numpy as np

_OPEN_KERNEL = np.ones((5, 5), np.uint8)
_CLOSE_KERNEL = np.ones((9, 9), np.uint8)


def _largest_blob_area_fraction(mask: np.ndarray) -> float:
    """Fraction of the frame covered by the largest *contiguous* masked
    region, not the raw masked-pixel count -- scattered individual pixels
    (a stray warm-colored object here, a shadow edge there) shouldn't
    count the same as one solid region, which is what an actual fire/smoke
    patch looks like."""
    if mask.size == 0:
        return 0.0
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _OPEN_KERNEL)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, _CLOSE_KERNEL)
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    largest = max(cv2.contourArea(c) for c in contours)
    return largest / (mask.shape[0] * mask.shape[1])


def fire_score(bgr_frame: np.ndarray) -> float:
    """Largest contiguous fire-colored region, as a fraction of frame area."""
    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)
    # OpenCV hue range is 0-179: 0-35 covers red through yellow-orange.
    # High saturation/value floors exclude dull/desaturated warm tones
    # (e.g. tanned skin, wood) that share the same hue range.
    color_mask = cv2.inRange(hsv, (0, 80, 140), (35, 255, 255))

    b, g, r = (bgr_frame[:, :, i].astype(np.int16) for i in range(3))
    # Classic rule-based fire-pixel test: red channel dominant, decreasing
    # toward blue, and bright enough to not just be a dark reddish surface.
    rgb_rule_mask = ((r > g) & (g > b) & (r > 150)).astype(np.uint8) * 255

    fire_mask = cv2.bitwise_and(color_mask, rgb_rule_mask)
    return _largest_blob_area_fraction(fire_mask)


def smoke_score(bgr_frame: np.ndarray, *, texture_threshold: float = 15.0, sky_exclude_fraction: float = 0.25) -> float:
    """Largest contiguous smoke-like (grey, hazy, low-texture) region below
    the excluded top-of-frame band, as a fraction of frame area. See this
    module's own docstring for why both the texture check and the sky
    exclusion exist -- neither is cosmetic, both were added after finding
    real false positives on this deployment's own camera feeds."""
    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)
    _, s, v = cv2.split(hsv)
    color_mask = ((s < 40) & (v > 90) & (v < 230)).astype(np.uint8) * 255

    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    edge_magnitude = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    # Blurred, not raw, edge magnitude: a real hazy/smoky region is smooth
    # over an *area*, not just pixel-to-pixel -- this keeps a handful of
    # sharp compression-noise pixels from disqualifying an otherwise-flat
    # patch, same reasoning as `_largest_blob_area_fraction`'s morphology.
    local_texture = cv2.blur(edge_magnitude, (15, 15))
    low_texture_mask = (local_texture < texture_threshold).astype(np.uint8) * 255

    smoke_mask = cv2.bitwise_and(color_mask, low_texture_mask)
    skip_rows = int(bgr_frame.shape[0] * sky_exclude_fraction)
    smoke_mask[:skip_rows, :] = 0

    return _largest_blob_area_fraction(smoke_mask)
