from app.rules.speed import estimate_kmh, pixel_distance
from app.schemas.internal import Point


def test_pixel_distance_is_euclidean() -> None:
    assert pixel_distance(Point(x=0, y=0), Point(x=3, y=4)) == 5.0


def test_estimate_kmh_basic_conversion() -> None:
    # Calibration: 10 (frame-percentage) pixels = 5 real-world meters.
    # Track moves 10 pixels in 1 second -> 5 m/s -> 18 km/h.
    kmh = estimate_kmh(
        pixels_moved=10.0, calibration_pixel_distance=10.0, calibration_real_world_meters=5.0,
        elapsed_seconds=1.0,
    )
    assert round(kmh, 1) == 18.0


def test_estimate_kmh_zero_when_no_time_elapsed() -> None:
    kmh = estimate_kmh(
        pixels_moved=10.0, calibration_pixel_distance=10.0, calibration_real_world_meters=5.0,
        elapsed_seconds=0.0,
    )
    assert kmh == 0.0


def test_estimate_kmh_zero_for_degenerate_calibration() -> None:
    kmh = estimate_kmh(
        pixels_moved=10.0, calibration_pixel_distance=0.0, calibration_real_world_meters=5.0,
        elapsed_seconds=1.0,
    )
    assert kmh == 0.0
