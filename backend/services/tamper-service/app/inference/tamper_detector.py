"""Camera tamper detection -- classical statistical baseline comparison,
NOT a trained model. doc09 §2.5 explicitly calls for this approach over a
learned detector: "a learned model would need per-deployment retraining
for scene changes, which classical statistical baselines handle for
free." This is the real, standard, industry technique for this problem
(frame-difference / histogram-comparison against a rolling baseline), not
a stand-in for something better that doesn't exist yet (unlike ANPR's
Haar-cascade fallback or Fire/Smoke's color heuristic, both stand-ins for
a model this deployment doesn't have) -- tamper detection genuinely
doesn't need a model in the first place.

Two features, tracked per camera as a slow (EMA) rolling baseline:
- A grayscale histogram (`cv2.compareHist` correlation against the
  baseline) -- catches a sudden full-frame color/brightness shift
  (covered, blacked out, or a materially different scene after being
  redirected).
- Edge density (fraction of Canny-edge pixels) -- catches a camera going
  out of focus or being covered by something textureless, which can
  leave the color histogram looking similar (e.g. covered by a grey
  cloth close to the lens's average color) but destroys fine detail.

Neither feature alone reliably distinguishes "covered" from "defocused"
from "redirected" -- doc09 §2.5 names these as the three things a
sustained deviation *typically* means, not three independently-detected
conditions. `classify_deviation` picks the most likely label for the
alert's description text; the alert itself is always the same
`event_type: "Camera Tamper"` regardless of which one tripped.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

_HISTOGRAM_BINS = 64  # coarser than 256 -- less sensitive to per-pixel noise, still plenty to catch a real shift


def _grayscale_histogram(bgr_frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [_HISTOGRAM_BINS], [0, 256])
    cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)  # frame-size-independent
    return hist.flatten()


def _edge_density(bgr_frame: np.ndarray) -> float:
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return float(np.count_nonzero(edges)) / edges.size


@dataclass(frozen=True)
class TamperReading:
    histogram_correlation: float  # 1.0 = identical to baseline, lower = more different
    edge_density: float
    edge_density_ratio: float  # current / baseline -- 1.0 = unchanged, near 0 = detail collapsed


class TamperBaseline:
    """One instance per camera. `compare()` never mutates state (safe to
    call every sampled frame); `update()` is the only thing that advances
    the EMA baseline, and callers must only invoke it on frames judged
    "normal" -- see `TamperService`, which freezes updates for the entire
    duration a deviation is flagged so a real tamper event never gets
    absorbed as "the new normal."."""

    def __init__(self, alpha: float = 0.05) -> None:
        self._alpha = alpha
        self._histogram: np.ndarray | None = None
        self._edge_density: float | None = None

    @property
    def is_initialized(self) -> bool:
        return self._histogram is not None

    def compare(self, frame: np.ndarray) -> TamperReading:
        edge_density = _edge_density(frame)
        if self._histogram is None or self._edge_density is None:
            # First-ever frame for this camera: nothing to compare against
            # yet: correlation/ratio of 1.0 ("identical to baseline") is
            # the correct "no deviation" reading, not a guess.
            return TamperReading(histogram_correlation=1.0, edge_density=edge_density, edge_density_ratio=1.0)

        histogram = _grayscale_histogram(frame)
        correlation = float(cv2.compareHist(self._histogram.astype(np.float32), histogram.astype(np.float32),
                                             cv2.HISTCMP_CORREL))
        edge_ratio = edge_density / self._edge_density if self._edge_density > 1e-6 else 1.0
        return TamperReading(
            histogram_correlation=correlation, edge_density=edge_density, edge_density_ratio=edge_ratio,
        )

    def update(self, frame: np.ndarray) -> None:
        histogram = _grayscale_histogram(frame)
        edge_density = _edge_density(frame)
        if self._histogram is None or self._edge_density is None:
            self._histogram = histogram
            self._edge_density = edge_density
            return
        self._histogram = (1 - self._alpha) * self._histogram + self._alpha * histogram
        self._edge_density = (1 - self._alpha) * self._edge_density + self._alpha * edge_density


def classify_deviation(
    reading: TamperReading,
    *,
    covered_correlation_threshold: float,
    redirected_correlation_threshold: float,
    defocus_edge_ratio_threshold: float,
) -> str | None:
    """Returns "covered", "defocused", "redirected", or None (no
    deviation) -- checked in this order because a fully covered/blacked
    lens crashes histogram correlation much harder than an ordinary scene
    change does, so the strictest color-based check should win first."""
    if reading.histogram_correlation < covered_correlation_threshold:
        return "covered"
    if reading.edge_density_ratio < defocus_edge_ratio_threshold:
        return "defocused"
    if reading.histogram_correlation < redirected_correlation_threshold:
        return "redirected"
    return None
