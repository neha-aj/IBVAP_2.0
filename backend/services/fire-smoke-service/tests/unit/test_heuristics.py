import numpy as np

from app.inference.heuristics import blood_score, fire_score, smoke_score


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


def test_fire_score_high_for_flickering_fire_colored_region() -> None:
    """Real flame has internal brightness variation (a bright core fading
    toward darker edges) -- this patch mimics that with a brighter
    yellow-orange core inside the wider orange region, not one flat color,
    so it should clear the variance check alongside the color/RGB one."""
    frame = _patch_frame(background=(80, 80, 80), patch=(0, 100, 255), patch_fraction=0.5)  # BGR orange
    frame[0:30, 0:30] = (0, 220, 255)  # brighter yellow-orange "core"
    assert fire_score(frame) > 0.15


def test_fire_score_zero_for_uniformly_colored_fire_hued_object() -> None:
    """A solid, uniformly-colored warm object (e.g. a red car) matches the
    color/RGB rule but has none of flame's internal brightness variation --
    must not read as fire. Reproduces a real false positive found on this
    deployment's own camera feed (a red car passing through frame)."""
    frame = _patch_frame(background=(80, 80, 80), patch=(0, 100, 255), patch_fraction=0.5)  # BGR orange, flat
    assert fire_score(frame) == 0.0


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


def test_blood_score_high_for_blood_colored_region() -> None:
    """A dark red/maroon patch -- low-to-moderate brightness, moderate-to-
    high saturation -- against a neutral grey background should clear the
    color mask and read as a sizeable contiguous region."""
    frame = _patch_frame(background=(80, 80, 80), patch=(20, 15, 110), patch_fraction=0.5)  # BGR dark maroon
    assert blood_score(frame) > 0.15


def test_blood_score_low_for_rust_colored_dirt() -> None:
    """Documented near-miss (see heuristics.py's docstring, point 4):
    rust/red-brown dirt is a real, disclosed expected failure mode for the
    blood color heuristic -- but this particular rust tone (brighter,
    more orange, and less saturated than dried blood's dark maroon) is
    chosen to fall outside the tuned value/saturation range, the same way
    `test_fire_score_zero_for_plain_green_frame` picks a clearly-outside
    color rather than an adversarial one."""
    frame = _patch_frame(background=(80, 80, 80), patch=(60, 90, 160), patch_fraction=0.5)  # BGR rust/red-brown
    assert blood_score(frame) < 0.1


def test_blood_score_low_for_sunlit_pavement_under_warm_light() -> None:
    """Reproduces this deployment's real, observed false positive (see
    heuristics.py's docstring, point 7): a driveway's grey concrete under
    golden-hour/sunset lighting, measured directly off that real camera
    frame at hue~6, saturation~83 (of 255), value~105 -- a warm-tinted but
    only moderately saturated surface, not genuinely saturated red. This
    is exactly what raising the saturation floor from 60 to 140 was fixed
    to reject; unlike `test_blood_score_low_for_rust_colored_dirt` (a
    hand-picked adversarial near-miss), this patch's color was taken
    directly from the real false-positive frame's own measured stats."""
    frame = _patch_frame(background=(80, 80, 80), patch=(71, 78, 105), patch_fraction=0.5)  # BGR, real measured hue/sat/value
    assert blood_score(frame) < 0.1


def test_blood_score_zero_for_plain_green_frame() -> None:
    frame = _solid_frame((0, 200, 0))  # BGR green -- outside the red/maroon hue bands
    assert blood_score(frame) == 0.0


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
