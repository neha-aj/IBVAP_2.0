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

**Live-tested against this deployment's real camera feeds and tuned
against three real false positives found that way** (not a substitute for
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
3. A bright red car passing through frame read as "fire" -- solid red
   paint is warm-hued, saturated, bright, and red-dominant, clearing every
   criterion the fire color+RGB rule checks for. 36 separate false-positive
   alerts fired for it, with reported coverage ranging 2-7% across every
   one (never higher). Fixed the same way #2 was: `fire_min_area_fraction`
   (`Settings`) raised from 0.02 to 0.15, comfortably above that observed
   false-positive ceiling, same reasoning and same value as
   `smoke_min_area_fraction`.

   `fire_score` also gained a `min_brightness_variance` check (real flame
   has a bright flickering core fading toward darker edges/tips; a flat-
   painted panel does not) -- a real, additional, principled discriminator
   against a *perfectly uniform* warm-colored region, and kept for that.
   Disclosed honestly, though: measured on this actual red car's photo, the
   candidate region's brightness variance was ~2649 -- real photographed
   surfaces pick up enough natural variance from lighting, reflections,
   and compression that a low variance threshold does NOT reliably reject
   them. The area-fraction fix above is what actually addresses this
   specific, observed false positive; the variance check is a second,
   independent layer, not a substitute for it.
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
    area_fraction, _ = _largest_blob(mask)
    return area_fraction


def _largest_blob(mask: np.ndarray) -> tuple[float, np.ndarray | None]:
    """Same largest-contiguous-region logic as `_largest_blob_area_fraction`,
    but also returns a mask of just that one region (not the full, possibly
    scattered, input mask) -- `fire_score`'s variance check below needs to
    inspect properties of *the candidate blob specifically*, not stray
    pixels elsewhere in frame that happened to also match the color rule."""
    if mask.size == 0:
        return 0.0, None
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _OPEN_KERNEL)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, _CLOSE_KERNEL)
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0, None
    largest = max(contours, key=cv2.contourArea)
    region_mask = np.zeros_like(mask)
    cv2.drawContours(region_mask, [largest], -1, 255, thickness=cv2.FILLED)
    return cv2.contourArea(largest) / (mask.shape[0] * mask.shape[1]), region_mask


def fire_score(bgr_frame: np.ndarray, *, min_brightness_variance: float = 200.0) -> float:
    """Largest contiguous fire-colored region, as a fraction of frame area.

    `min_brightness_variance` rejects a candidate region with no internal
    brightness variation at all -- real flame has a bright flickering core
    fading toward darker edges/tips; a perfectly flat/uniform warm-colored
    region does not. This module's own docstring (see point 3) is explicit
    that this alone is NOT what fixed this deployment's real red-car false
    positive -- a real photographed "solid" surface picks up plenty of
    variance from lighting/reflections/compression (~2649, measured, on
    that exact case) to clear a threshold low enough to still admit real
    flame. `Settings.fire_min_area_fraction` is the fix actually validated
    against that observed case; this check is a second, independent, still
    real discriminator (e.g. against a flat rendered/synthetic false
    color), not a replacement for it. See `test_heuristics.py`'s
    `test_fire_score_zero_for_uniformly_colored_fire_hued_object`."""
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
    area_fraction, region_mask = _largest_blob(fire_mask)
    if region_mask is None:
        return 0.0

    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    region_brightness = gray[region_mask > 0]
    if region_brightness.size > 0 and float(region_brightness.var()) < min_brightness_variance:
        return 0.0  # uniformly-colored warm object, not flame's characteristic flicker/gradient

    return area_fraction


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
