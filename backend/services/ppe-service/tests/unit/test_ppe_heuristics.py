import numpy as np

from app.inference.ppe_heuristics import classify_ppe, vest_coverage_fraction


def _solid_color_crop(bgr: tuple[int, int, int], height: int = 100, width: int = 60) -> np.ndarray:
    crop = np.zeros((height, width, 3), dtype=np.uint8)
    crop[:, :] = bgr
    return crop


def test_hi_vis_orange_torso_scores_high_coverage() -> None:
    # BGR safety orange.
    crop = _solid_color_crop((0, 100, 255))
    assert vest_coverage_fraction(crop) > 0.9


def test_hi_vis_yellow_torso_scores_high_coverage() -> None:
    # BGR safety yellow.
    crop = _solid_color_crop((0, 255, 255))
    assert vest_coverage_fraction(crop) > 0.9


def test_plain_dark_clothing_scores_low_coverage() -> None:
    # BGR dark navy -- low saturation/value, must not read as hi-vis.
    crop = _solid_color_crop((60, 40, 20))
    assert vest_coverage_fraction(crop) < 0.05


def test_skin_tone_does_not_false_positive_as_hi_vis() -> None:
    # A desaturated tan/skin tone must not cross the saturation floor.
    crop = _solid_color_crop((150, 180, 210))
    assert vest_coverage_fraction(crop) < 0.3


def test_empty_crop_scores_zero() -> None:
    assert vest_coverage_fraction(np.zeros((0, 0, 3), dtype=np.uint8)) == 0.0


def test_classify_ppe_flags_missing_vest_below_threshold() -> None:
    crop = _solid_color_crop((60, 40, 20))
    assert classify_ppe(crop, vest_min_coverage_fraction=0.12) == ["vest"]


def test_classify_ppe_passes_when_vest_present() -> None:
    crop = _solid_color_crop((0, 100, 255))
    assert classify_ppe(crop, vest_min_coverage_fraction=0.12) == []
