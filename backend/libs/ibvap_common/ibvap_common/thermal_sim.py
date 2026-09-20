"""Simulated thermal rendering of an ordinary (RGB) video frame.

There is no thermal hardware in this deployment, so a camera can opt in to a
*derived* thermal view: the ingestion service renders one for the live
preview, and the detection service renders the identical one from the same
frame to run detection on it -- both call `simulate_thermal`, so what an
operator sees is exactly what was analysed.

This is an approximation, not a measurement. Real thermal imaging reads
emitted heat, which a colour image doesn't contain. The rendering uses
brightness plus a "warmth" cue (red-dominant pixels -- skin, clothing,
fire, vehicle bodies -- read hotter than blue-dominant ones such as sky),
local-contrast equalisation, a light blur (thermal sensors are soft), and an
inferno false-colour palette. People and vehicles generally stand out, but
it can't reveal anything the RGB frame didn't already show.
"""

from __future__ import annotations

import cv2
import numpy as np

from ibvap_common.derived_thermal import DERIVED_THERMAL_SOURCE, is_derived_thermal  # noqa: F401 -- re-exported

_WARMTH_WEIGHT = 0.35


def simulate_thermal(bgr: np.ndarray) -> np.ndarray:
    """Returns a BGR false-colour "thermal" rendering of `bgr`, same size."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blue = bgr[:, :, 0].astype(np.float32)
    red = bgr[:, :, 2].astype(np.float32)
    warmth = (red - blue + 255.0) / 2.0  # 0 (very blue) .. 255 (very red), 127.5 neutral
    heat = np.clip((1.0 - _WARMTH_WEIGHT) * gray + _WARMTH_WEIGHT * warmth, 0, 255).astype(np.uint8)
    # Built per call: cv2 CLAHE objects aren't safe to share across the
    # threads several camera consumers call this from at once.
    heat = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(heat)
    heat = cv2.GaussianBlur(heat, (3, 3), 0)
    return cv2.applyColorMap(heat, cv2.COLORMAP_INFERNO)
