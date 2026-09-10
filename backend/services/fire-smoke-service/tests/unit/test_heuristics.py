import numpy as np

from app.inference.heuristics import fire_score, smoke_score


def _solid_frame(bgr_color: tuple[int, int, int], size: int = 120) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    frame[:, :] = bgr_color
    return frame


def _patch_frame(background: tuple[int, int, int], patch: tuple[int, int, int], size: int = 120,
                  patch_fraction: float = 0.4, row_offset_fraction: float = 0.0) -> np.ndarray:
    frame = _solid_frame(background, size)
    patch_size = int(size * patch_fraction)
    row_start = int(size * row_offset_fraction)
    frame[row_start:row_start + patch_size, 0:patch_size] = patch
    return frame


def test_fire_score_high_for_solid_fire_colored_region() -> None:
    frame = _patch_frame(background=(80, 80, 80), patch=(0, 100, 255), patch_fraction=0.5)  # BGR orange
    assert fire_score(frame) > 0.15


def test_fire_score_zero_for_plain_green_frame() -> None:
    frame = _solid_frame((0, 200, 0))  # BGR green -- not R>G>B
    assert fire_score(frame) == 0.0


def test_smoke_score_high_for_solid_grey_region() -> None:
    # Placed below the default 25% sky-exclusion band, not at the top --
    # see test_smoke_score_zero_for_region_entirely_in_sky_band below for
    # the case where it *is* at the top.
    frame = _patch_frame(background=(0, 200, 0), patch=(150, 150, 150), patch_fraction=0.5,
                          row_offset_fraction=0.3)
    assert smoke_score(frame) > 0.15


def test_smoke_score_zero_for_saturated_color_frame() -> None:
    frame = _solid_frame((0, 200, 0))  # high saturation -- not grey/hazy
    assert smoke_score(frame) == 0.0


def test_smoke_score_zero_for_region_entirely_in_sky_band() -> None:
    """A uniform grey region that only ever appears in the excluded
    top-of-frame band (real deployment case: an overcast sky) must not
    read as smoke -- see heuristics.py's own docstring for why this
    exclusion exists and what it trades away."""
    frame = _patch_frame(background=(0, 200, 0), patch=(150, 150, 150), patch_fraction=0.2,
                          row_offset_fraction=0.0)
    assert smoke_score(frame, sky_exclude_fraction=0.25) == 0.0


def test_smoke_score_zero_for_textured_grey_region() -> None:
    """A grey-toned but *textured* region (real deployment case: plain
    sandy/paved ground, which has visible grain/cracks even though it's
    low-saturation) must not read as smoke -- the texture check is what
    tells it apart from an actually-smooth hazy region."""
    rng = np.random.default_rng(seed=1)
    frame = _solid_frame((0, 200, 0))
    noise = rng.integers(100, 200, size=(120, 120), dtype=np.uint8)
    frame[40:100, 0:60] = np.stack([noise[40:100, 0:60]] * 3, axis=-1)
    assert smoke_score(frame) < 0.1


def test_fire_score_ignores_scattered_non_contiguous_pixels() -> None:
    """A handful of scattered fire-colored pixels (e.g. compression noise)
    must not count the same as one solid fire-sized region -- the whole
    point of using largest-contiguous-blob area rather than raw masked
    pixel count."""
    frame = _solid_frame((80, 80, 80))
    rng = np.random.default_rng(seed=0)
    ys = rng.integers(0, 120, size=30)
    xs = rng.integers(0, 120, size=30)
    frame[ys, xs] = (0, 100, 255)
    assert fire_score(frame) < 0.02
