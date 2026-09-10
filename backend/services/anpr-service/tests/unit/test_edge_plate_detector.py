import numpy as np

from app.inference.edge_plate_detector import detect_by_edge_density


def _crop_with_plate_stripes(height: int = 120, width: int = 200) -> np.ndarray:
    """A smooth gray background with a small, wide band of alternating
    vertical stripes (stand-in for a plate's dense character edges) at a
    plausible plate aspect ratio and position -- everywhere else has no
    strong vertical gradient at all."""
    crop = np.full((height, width), 120, dtype=np.uint8)
    plate_y, plate_h = 60, 20
    plate_x, plate_w = 60, 80  # 80x20 -- aspect ratio 4.0, within range
    stripes = crop[plate_y : plate_y + plate_h, plate_x : plate_x + plate_w]
    stripes[:, ::4] = 20
    stripes[:, 1::4] = 220
    return crop


def test_finds_plate_shaped_edge_cluster() -> None:
    crop = _crop_with_plate_stripes()

    result = detect_by_edge_density(crop)

    assert result is not None
    x, y, w, h = result
    assert h > 0
    aspect_ratio = w / h
    assert 2.0 <= aspect_ratio <= 6.0
    # The found region should overlap the actual stripe band, not some
    # unrelated part of the smooth background.
    assert 40 <= x <= 100
    assert 40 <= y <= 100


def test_empty_crop_returns_none() -> None:
    assert detect_by_edge_density(np.zeros((0, 0), dtype=np.uint8)) is None


def test_uniform_blank_crop_finds_nothing() -> None:
    """No edges anywhere -- a plain gray crop must never produce a false
    candidate."""
    crop = np.full((100, 150), 128, dtype=np.uint8)
    assert detect_by_edge_density(crop) is None


def test_respects_custom_aspect_ratio_bounds() -> None:
    """A region that would otherwise qualify is excluded once the caller's
    aspect-ratio window no longer covers it."""
    crop = _crop_with_plate_stripes()

    assert detect_by_edge_density(crop, min_aspect_ratio=10.0, max_aspect_ratio=20.0) is None
