import cv2
import numpy as np

from app.inference.tamper_detector import TamperBaseline, classify_deviation

_THRESHOLDS = {
    "covered_correlation_threshold": 0.5, "redirected_correlation_threshold": 0.75, "defocus_edge_ratio_threshold": 0.3,
}


def _noisy_scene(seed: int, low: int = 0, high: int = 256, size: int = 160) -> np.ndarray:
    """Stands in for a real, detailed camera scene: has genuine edges
    (Canny fires readily on high-frequency noise) and a real histogram
    shape -- unlike a solid color frame, which has neither."""
    rng = np.random.default_rng(seed)
    gray = rng.integers(low, high, size=(size, size), dtype=np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


def _blocky_scene(seed: int, low: int = 40, high: int = 220, block: int = 32, size: int = 160) -> np.ndarray:
    """A more realistic stand-in for actual video content than raw IID
    noise: real scenes are spatially correlated (a wall, a road, a shirt
    are each one roughly-uniform region), so a *moderate* blur only
    perturbs values near region *boundaries*, not the whole frame's value
    distribution the way it does for pure per-pixel noise -- pure noise
    (or noise with blocks much smaller than the blur radius) makes blur
    look far more like a full-frame "covered" event than realistic
    defocus does."""
    rng = np.random.default_rng(seed)
    blocks_per_side = size // block
    small = rng.integers(low, high, size=(blocks_per_side, blocks_per_side), dtype=np.uint8)
    gray = np.kron(small, np.ones((block, block), dtype=np.uint8))
    return np.stack([gray, gray, gray], axis=-1)


def _partially_different_scene(seed: int, change_seed: int, change_fraction: float = 0.4,
                                low: int = 40, high: int = 220, block: int = 32, size: int = 160) -> np.ndarray:
    """A real "camera redirected" case keeps roughly the same lighting/
    exposure (same physical environment) but shows different content --
    unlike two fully independent random scenes, which can differ far more
    than an actual pan/redirect would (there's no shared structure at
    all), making the "redirected" bucket look artificially identical to
    "covered" in a synthetic test that isn't representative of real
    footage."""
    rng = np.random.default_rng(seed)
    blocks_per_side = size // block
    small = rng.integers(low, high, size=(blocks_per_side, blocks_per_side), dtype=np.uint8)
    change_rng = np.random.default_rng(change_seed)
    mask = change_rng.random(small.shape) < change_fraction
    small[mask] = change_rng.integers(low, high, size=int(mask.sum()), dtype=np.uint8)
    gray = np.kron(small, np.ones((block, block), dtype=np.uint8))
    return np.stack([gray, gray, gray], axis=-1)


def _blurred(frame: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(frame, (13, 13), sigmaX=4)


def test_first_frame_has_no_deviation() -> None:
    baseline = TamperBaseline()
    reading = baseline.compare(_noisy_scene(seed=1))
    assert classify_deviation(reading, **_THRESHOLDS) is None


def test_identical_scene_has_no_deviation_after_baseline_set() -> None:
    baseline = TamperBaseline()
    scene = _noisy_scene(seed=1)
    baseline.update(scene)
    reading = baseline.compare(scene)
    assert classify_deviation(reading, **_THRESHOLDS) is None


def test_solid_frame_classified_as_covered() -> None:
    baseline = TamperBaseline()
    baseline.update(_noisy_scene(seed=1))
    covered_frame = np.zeros((160, 160, 3), dtype=np.uint8)
    reading = baseline.compare(covered_frame)
    assert classify_deviation(reading, **_THRESHOLDS) == "covered"


def test_heavily_blurred_scene_classified_as_defocused() -> None:
    scene = _blocky_scene(seed=1)
    baseline = TamperBaseline()
    baseline.update(scene)
    reading = baseline.compare(_blurred(scene))
    assert classify_deviation(reading, **_THRESHOLDS) == "defocused"


def test_partially_different_scene_classified_as_redirected() -> None:
    """Same overall brightness range and block structure (still a real,
    detailed scene, not covered/defocused) but enough content changed --
    a real "camera pointed somewhere else now" case, not a brightness or
    focus change."""
    baseline = TamperBaseline()
    baseline.update(_blocky_scene(seed=1))
    reading = baseline.compare(_partially_different_scene(seed=1, change_seed=99))
    assert classify_deviation(reading, **_THRESHOLDS) == "redirected"


def test_baseline_adapts_toward_gradual_change() -> None:
    """Repeated `update()` calls should pull the baseline toward a new
    (gradually-shifted) scene, so a real slow lighting change doesn't
    stay flagged forever -- unlike a tamper event, which never calls
    `update()` while flagged (that's TamperService's job, not the
    baseline's, but the baseline must still be capable of drifting when
    told to)."""
    baseline = TamperBaseline(alpha=0.3)
    original = _noisy_scene(seed=1, low=0, high=120)
    shifted = _noisy_scene(seed=1, low=40, high=160)  # a bit brighter, same texture
    baseline.update(original)
    for _ in range(30):
        baseline.update(shifted)
    reading = baseline.compare(shifted)
    assert reading.histogram_correlation > 0.9
