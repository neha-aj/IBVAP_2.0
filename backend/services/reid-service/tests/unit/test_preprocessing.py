import numpy as np

from app.inference.preprocessing import crop_bbox_percent


def _frame(height: int = 100, width: int = 200) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_crop_bbox_percent_extracts_correct_region() -> None:
    frame = _frame(height=100, width=200)
    crop = crop_bbox_percent(frame, x=10.0, y=20.0, width=50.0, height=25.0)
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
