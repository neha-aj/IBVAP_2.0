"""Simulated thermal rendering of an ordinary (RGB) video.

There is no thermal hardware in this deployment, so a camera can opt in to a
*derived* thermal view. Ingestion renders it once per captured frame with a
`ThermalSimulator`, shows it as the thermal tile, and ships the very same image
alongside the RGB frame so detection analyses exactly what the operator sees.

What real thermal footage looks like -- and what this imitates: a cold,
near-black-to-blue world where the static scene sits near ambient temperature
and warm bodies (people, animals, running vehicles) glow orange/yellow with a
cooler green/cyan halo. A colour image contains no heat, so "warm" is inferred
from *movement*: a learned background is treated as cold, and whatever moves
against it is rendered hot, with a soft glow and a short afterglow. Something
that stops moving stays visibly warm for a while, then cools as it's absorbed
into the background; where something *left* (a "ghost" of the old background)
the model re-learns the scene within a few seconds.

It is a simulation, not a measurement. It cannot show anything the video
didn't already show, and warm-but-still things (a parked car's engine) read as
cold. It assumes a fixed camera: if the camera itself moves, everything appears to
move and the glow follows edges rather than bodies. The pure per-frame `simulate_thermal` below (ambient tones only, no
motion) is a fallback for frames that arrive without a rendered thermal image.
"""

from __future__ import annotations

import time
from functools import lru_cache

import cv2
import numpy as np

from ibvap_common.derived_thermal import DERIVED_THERMAL_SOURCE, is_derived_thermal  # noqa: F401 -- re-exported

# --- look -----------------------------------------------------------------
# The scene sits in the dark end of the palette (black .. navy .. blue),
# leaving the rest for hot things (cyan -> green -> yellow -> orange -> red).
_AMBIENT_FLOOR = 0.03
_AMBIENT_SPAN = 0.21
_HOT_CEILING = 0.92
_OUT_WIDTH = 960  # thermal sensors are low-res; also keeps the encoded frame small

# Thermal "rainbow" palette anchors: (position, R, G, B).
_PALETTE = (
    (0.00, 0, 0, 8),
    (0.14, 8, 6, 88),
    (0.28, 10, 30, 200),
    (0.40, 0, 150, 255),
    (0.50, 0, 235, 200),
    (0.58, 60, 255, 60),
    (0.68, 220, 255, 0),
    (0.78, 255, 190, 0),
    (0.87, 255, 90, 0),
    (0.95, 235, 20, 20),
    (1.00, 255, 220, 220),
)


def _build_lut() -> np.ndarray:
    xs = np.linspace(0.0, 1.0, 256)
    pos = [p[0] for p in _PALETTE]
    rgb = np.stack([np.interp(xs, pos, [p[i] for p in _PALETTE]) for i in (1, 2, 3)], axis=1)
    return np.ascontiguousarray(rgb[:, ::-1].astype(np.uint8).reshape(256, 1, 3))  # BGR, as cv2 expects


_LUT = _build_lut()


@lru_cache(maxsize=1)
def _palette_inverse() -> np.ndarray:
    """(32, 32, 32) table: BGR colour (5 bits per channel) -> nearest palette
    heat index. Built on first use; cheap enough (a few ms of numpy)."""
    palette = _LUT.reshape(256, 3).astype(np.int32)
    centres = np.arange(32) * 8 + 4
    b, g, r = np.meshgrid(centres, centres, centres, indexing="ij")
    cells = np.stack([b.ravel(), g.ravel(), r.ravel()], axis=1).astype(np.int32)
    nearest = np.empty(len(cells), np.uint8)
    for start in range(0, len(cells), 4096):  # chunked: keeps the distance matrix small
        chunk = cells[start:start + 4096]
        nearest[start:start + 4096] = ((chunk[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return nearest.reshape(32, 32, 32)


def to_detection_view(thermal_bgr: np.ndarray) -> np.ndarray:
    """The same heat data as a "white-hot" greyscale image (hotter = brighter),
    for running object detection on.

    The false-colour rendering is what an operator wants to look at, but a
    detector trained on ordinary photos barely recognises people in glowing
    blue/orange blobs (in testing: none, versus most of them in white-hot).
    Thermal analytics conventionally works on white-hot for this reason. Uses a
    fixed scale, so a scene with nothing hot in it stays dark rather than being
    stretched to full brightness."""
    heat = _palette_inverse()[thermal_bgr[..., 0] >> 3, thermal_bgr[..., 1] >> 3, thermal_bgr[..., 2] >> 3]
    grey = np.minimum(heat.astype(np.float32) * (255.0 / (_HOT_CEILING * 255.0)), 255.0).astype(np.uint8)
    return cv2.merge([grey, grey, grey])

# --- motion / background model ----------------------------------------------
_WORK_WIDTH = 480  # model runs at this width; the result is scaled back up
_NOISE_FLOOR = 14.0  # colour difference (0-255) below which nothing counts as different
_MOTION_SPAN = 26.0  # ...and how far above it a pixel must be to count as fully different
_ACTIVITY_LAG = 0.2  # s: movement is measured against a frame this far back, so it doesn't depend on the frame rate
_ACTIVITY_NOISE = 9.0  # colour difference over that window that counts as something actually moving
_ACTIVITY_SPAN = 20.0
_TAU_BG_QUIET = 1.2  # s: background re-learns fast where nothing is moving (clears "ghosts")
_TAU_BG_ACTIVE = 25.0  # s: ...and slowly where something is moving (it stays warm)
_TAU_ACTIVITY = 1.0  # s: how long a region counts as "moving" after its last movement
_TAU_AFTERGLOW = 0.18  # s: how long heat lingers behind a moving body (kept short: longer smears walkers)
_STILL_WARMTH = 0.38  # how warm something reads that differs from the background but isn't moving
_WARMUP_S = 1.5  # after a (re)start the background is learned before anything can glow
_SCENE_CUT_FRACTION = 0.45  # more of the frame than this "different" at once = a cut/loop, not motion


def _smoothstep(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _ambient(gray_u8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cool base layer (0..1) from brightness -- local-contrast equalised so
    walls, floors and edges stay legible -- squeezed into the cold end of the
    palette, with very bright light sources nudged warmer. Also returns the
    equalised brightness (0..1), used to texture the inside of warm bodies."""
    # Built per call: cv2 CLAHE objects aren't safe to share across threads.
    eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6, 6)).apply(gray_u8).astype(np.float32) / 255.0
    lamp = _smoothstep(gray_u8.astype(np.float32), 232.0, 255.0)
    return _AMBIENT_FLOOR + _AMBIENT_SPAN * eq + 0.16 * lamp, eq


def _max_abs_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-pixel largest absolute difference across the colour channels. (Done
    with OpenCV's element-wise ops: numpy's reduce over a 3-wide last axis is
    several times slower.)"""
    c0, c1, c2 = cv2.split(cv2.absdiff(a, b))
    return cv2.max(cv2.max(c0, c1), c2)


def _colorize(value: np.ndarray, out_size: tuple[int, int]) -> np.ndarray:
    """0..1 heat map -> BGR false-colour image at `out_size`."""
    v = np.clip(value * 255.0, 0, 255).astype(np.uint8)
    bgr = cv2.LUT(cv2.merge([v, v, v]), _LUT)
    if (bgr.shape[1], bgr.shape[0]) != out_size:
        bgr = cv2.resize(bgr, out_size, interpolation=cv2.INTER_LINEAR)
    return bgr


def _downscale(bgr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Area-average `bgr` down to `size`, decimating big frames first (a plain
    stride view is free) so the expensive resize starts from a smaller image."""
    h, w = bgr.shape[:2]
    if (w, h) == size:
        return bgr
    k = min(w // size[0], h // size[1])
    if k >= 2:
        bgr = bgr[::k, ::k]
    return cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)


def _out_size(w: int, h: int, out_width: int) -> tuple[int, int]:
    scale = min(1.0, out_width / w)
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


class ThermalSimulator:
    """One per camera. Feed it consecutive frames of the same video."""

    def __init__(self, work_width: int = _WORK_WIDTH, out_width: int = _OUT_WIDTH) -> None:
        self._work_width = work_width
        self._out_width = out_width
        self.reset()

    def reset(self) -> None:
        """Forget the learned background (call on a scene change, e.g. a
        looping file restarting)."""
        self._bg: np.ndarray | None = None
        self._ref: np.ndarray | None = None
        self._ref_t: float | None = None
        self._heat: np.ndarray | None = None
        self._activity: np.ndarray | None = None
        self._last_t: float | None = None
        self._started_at: float | None = None

    def render(self, bgr: np.ndarray, now: float | None = None) -> np.ndarray:
        """Returns the BGR thermal rendering of this frame. Its size is the
        frame's, capped at `out_width` wide (aspect ratio kept)."""
        now = time.monotonic() if now is None else now
        h, w = bgr.shape[:2]
        scale = min(1.0, self._work_width / w)
        size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        small = _downscale(bgr, size)
        frame = cv2.GaussianBlur(small, (0, 0), 1.0).astype(np.float32)

        if self._bg is None or self._bg.shape != frame.shape:
            self._start(frame, now)
        else:
            self._update(frame, now)

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        ambient, eq = _ambient(gray)
        ambient = cv2.GaussianBlur(ambient, (0, 0), 1.2)
        # A tight core plus a wider bloom: hot in the middle of a body, cooling
        # through green/cyan at its edges like a real sensor's optics; the
        # brightness texture keeps clothing/limbs from rendering as flat blobs.
        core = cv2.GaussianBlur(self._heat, (0, 0), 2.0)
        half = cv2.resize(self._heat, (max(1, size[0] // 2), max(1, size[1] // 2)), interpolation=cv2.INTER_AREA)
        bloom = cv2.resize(cv2.GaussianBlur(half, (0, 0), 2.2), size, interpolation=cv2.INTER_LINEAR)
        hot = np.clip(1.4 * core + 0.3 * bloom, 0.0, 1.0)
        hot = np.clip(hot * (0.86 + 0.28 * (eq - 0.5)), 0.0, 1.0)
        value = ambient + (_HOT_CEILING - ambient) * hot
        return _colorize(value, _out_size(w, h, self._out_width))

    def _start(self, frame: np.ndarray, now: float) -> None:
        self._bg = frame.copy()
        self._ref = frame
        self._ref_t = now
        self._heat = np.zeros(frame.shape[:2], np.float32)
        self._activity = np.zeros(frame.shape[:2], np.float32)
        self._last_t = now
        self._started_at = now

    def _update(self, frame: np.ndarray, now: float) -> None:
        dt = float(np.clip(now - (self._last_t if self._last_t is not None else now), 0.005, 1.0))
        self._last_t = now

        # Where things are moving *right now* (frame-to-frame), remembered for
        # about a second: tells a real mover from a static difference to the
        # background (a ghost, or someone standing still).
        step = _max_abs_diff(frame, self._ref)
        if now - (self._ref_t if self._ref_t is not None else now) >= _ACTIVITY_LAG:
            self._ref, self._ref_t = frame, now
        moving = np.clip((step - _ACTIVITY_NOISE) / _ACTIVITY_SPAN, 0.0, 1.0)
        moving = cv2.dilate(cv2.GaussianBlur(moving, (0, 0), 3.0), np.ones((7, 7), np.uint8))
        self._activity = np.maximum(np.clip(moving * 2.0, 0.0, 1.0), self._activity * float(np.exp(-dt / _TAU_ACTIVITY)))

        diff = _max_abs_diff(frame, self._bg)
        different = np.clip((diff - _NOISE_FLOOR) / _MOTION_SPAN, 0.0, 1.0)
        different = cv2.morphologyEx(different, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        if np.count_nonzero(different > 0.5) > _SCENE_CUT_FRACTION * different.size:
            # A cut (or a looping file restarting): everything "different" at
            # once is a new scene, not a crowd.
            self._start(frame, now)
            return

        started_at = self._started_at if self._started_at is not None else now
        warming_up = (now - started_at) < _WARMUP_S
        tau_active = _TAU_BG_QUIET if warming_up else _TAU_BG_ACTIVE
        adapt_quiet = 1.0 - np.exp(-dt / _TAU_BG_QUIET)
        adapt_active = 1.0 - np.exp(-dt / tau_active)
        alpha = np.where(self._activity > 0.25, adapt_active, adapt_quiet).astype(np.float32)[..., None]
        self._bg += alpha * (frame - self._bg)

        if warming_up:
            return  # still learning the scene: nothing glows yet
        # Different-and-moving is fully hot; different-but-still is only warm.
        intensity = different * (_STILL_WARMTH + (1.0 - _STILL_WARMTH) * self._activity)
        self._heat = np.maximum(intensity, self._heat * float(np.exp(-dt / _TAU_AFTERGLOW)))


def simulate_thermal(bgr: np.ndarray) -> np.ndarray:
    """Pure, stateless fallback: the cool ambient look only (no motion, so
    nothing glows). Used when a frame arrives without a rendered thermal image."""
    h, w = bgr.shape[:2]
    scale = min(1.0, _WORK_WIDTH / w)
    small = _downscale(bgr, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))))
    ambient, _ = _ambient(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    return _colorize(cv2.GaussianBlur(ambient, (0, 0), 1.2), _out_size(w, h, _OUT_WIDTH))
