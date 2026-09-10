import numpy as np

from app.inference.preprocessing import crop_bbox_percent, normalize_for_ocr, upscale_if_small


def _frame(height: int = 100, width: int = 200) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_crop_bbox_percent_extracts_correct_region() -> None:
    frame = _frame(height=100, width=200)
    crop = crop_bbox_percent(frame, x=10.0, y=20.0, width=50.0, height=25.0)
    # x: 10%-60% of 200 = 20-120 (100px wide); y: 20%-45% of 100 = 20-45 (25px tall)
    assert crop.shape[1] == 100
    assert crop.shape[0] == 25


def test_crop_bbox_percent_clamps_to_frame_bounds() -> None:
    frame = _frame()
    crop = crop_bbox_percent(frame, x=90.0, y=90.0, width=50.0, height=50.0)
    assert crop.shape[0] <= frame.shape[0]
    assert crop.shape[1] <= frame.shape[1]


def test_crop_bbox_percent_empty_for_degenerate_box() -> None:
    frame = _frame()
    crop = crop_bbox_percent(frame, x=50.0, y=50.0, width=0.0, height=0.0)
    assert crop.size == 0


def test_upscale_if_small_scales_up_short_crops() -> None:
    crop = np.zeros((20, 40, 3), dtype=np.uint8)
    result = upscale_if_small(crop, min_height_px=64)
    assert result.shape[0] == 64
    assert result.shape[1] == 128  # aspect ratio preserved (64/20 = 3.2x scale)


def test_upscale_if_small_leaves_tall_enough_crops_alone() -> None:
    crop = np.zeros((100, 40, 3), dtype=np.uint8)
    result = upscale_if_small(crop, min_height_px=64)
    assert result.shape == crop.shape


def test_upscale_if_small_handles_empty_crop() -> None:
    crop = np.zeros((0, 0, 3), dtype=np.uint8)
    result = upscale_if_small(crop, min_height_px=64)
    assert result.size == 0


def test_normalize_for_ocr_returns_grayscale() -> None:
    crop = np.zeros((50, 50, 3), dtype=np.uint8)
    result = normalize_for_ocr(crop)
    assert result.ndim == 2
