"""Speed Estimation rule (Phase 2 doc09 §1.2): pixel displacement between
two centroid readings, divided by elapsed time, converted to km/h via a
per-camera calibration (two reference points a known real-world distance
apart -- `camera.cameras.calibration`, set once by an admin). Pure -- the
engine owns "what was the previous centroid/timestamp" bookkeeping."""

from __future__ import annotations

from app.schemas.internal import Point


def pixel_distance(a: Point, b: Point) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def estimate_kmh(*, pixels_moved: float, calibration_pixel_distance: float, calibration_real_world_meters: float,
                  elapsed_seconds: float) -> float:
    """`calibration_pixel_distance`/`calibration_real_world_meters` together
    define meters-per-pixel-of-the-same-normalized-frame-space every bbox
    coordinate already uses. Returns 0 for a non-positive elapsed time (two
    updates landing in the same instant) rather than raising -- callers loop
    over many tracks and one degenerate reading shouldn't break the rest."""
    if elapsed_seconds <= 0 or calibration_pixel_distance <= 0:
        return 0.0
    meters_per_pixel = calibration_real_world_meters / calibration_pixel_distance
    meters_moved = pixels_moved * meters_per_pixel
    meters_per_second = meters_moved / elapsed_seconds
    return meters_per_second * 3.6
