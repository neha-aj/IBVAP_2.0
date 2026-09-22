"""The simulated thermal view: a cold, dark-blue scene in which whatever moves
glows hot. These use synthetic frames with explicit timestamps, so they are
deterministic and independent of the machine's speed."""

import cv2
import numpy as np
import pytest

from ibvap_common.thermal_sim import ThermalSimulator, simulate_thermal

W, H = 320, 180
FPS = 30


def _background(seed: int = 0) -> np.ndarray:
    """A static, textured grey scene."""
    rng = np.random.default_rng(seed)
    base = np.tile(np.linspace(70, 150, W, dtype=np.float32), (H, 1))
    noise = rng.normal(0, 3, (H, W)).astype(np.float32)
    grey = np.clip(base + noise, 0, 255).astype(np.uint8)
    return cv2.merge([grey, grey, grey])


def _with_object(bg: np.ndarray, x: int, y: int = 60, size: int = 40, value: int = 235) -> np.ndarray:
    frame = bg.copy()
    frame[y:y + size, x:x + size] = value
    return frame


def _hot(out: np.ndarray) -> np.ndarray:
    """Pixels rendered in the warm half of the palette (yellow/orange/red)."""
    return (out[..., 2] > 150) & (out[..., 0] < 100)


def _run(sim: ThermalSimulator, frames, start: float = 5.0):
    out = None
    for i, frame in enumerate(frames):
        out = sim.render(frame, now=start + i / FPS)
    return out


# --- the look ----------------------------------------------------------------

def test_a_static_scene_stays_cold_and_blue() -> None:
    bg = _background()
    out = _run(ThermalSimulator(), [bg] * 90)

    assert _hot(out).sum() == 0
    assert out[..., 0].mean() > out[..., 2].mean()  # blue dominates red: the scene is cold


def test_something_moving_glows_hot_where_it_is_and_only_there() -> None:
    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75)  # learn the scene (past the warm-up)
    frames = [_with_object(bg, x) for x in range(20, 120, 4)]  # walks right across the frame
    out = _run(sim, frames, start=5.0 + 75 / FPS)

    hot = _hot(out)
    assert hot.sum() > 100
    ys, xs = np.nonzero(hot)
    last_x = 20 + 4 * (len(frames) - 1)
    assert last_x - 25 <= xs.mean() <= last_x + 65  # centred on (or just behind) where it is now
    assert not hot[:, 200:].any()  # nothing glows on the far side of the frame


def test_hot_regions_read_as_warm_colours_and_the_background_as_cool_ones() -> None:
    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75)
    out = _run(sim, [_with_object(bg, x) for x in range(20, 100, 4)], start=5.0 + 75 / FPS)

    hot = _hot(out)
    assert out[hot][:, 2].mean() > out[hot][:, 0].mean()  # hot: red > blue
    cold = out[:, 250:]
    assert cold[..., 0].mean() > cold[..., 2].mean()  # background: blue > red


def test_a_moving_object_that_has_left_stops_glowing() -> None:
    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75)
    _run(sim, [_with_object(bg, x) for x in range(20, 120, 4)], start=5.0 + 75 / FPS)
    out = _run(sim, [bg] * 300, start=20.0)  # 10 s of an empty scene

    assert _hot(out).sum() == 0


def test_a_ghost_of_something_that_was_there_at_the_start_fades() -> None:
    """The first frame contains an object that then leaves: the model briefly
    sees a 'difference' where it stood, and must re-learn rather than glow."""
    bg = _background()
    sim = ThermalSimulator()
    out = _run(sim, [_with_object(bg, 100)] * 30 + [bg] * 300)

    assert _hot(out).sum() == 0


def test_something_that_stops_moving_stays_warm_for_a_while_then_cools() -> None:
    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75)
    t = 5.0 + 75 / FPS
    _run(sim, [_with_object(bg, x) for x in range(20, 100, 4)], start=t)
    t += 20 / FPS
    stopped = _with_object(bg, 96)
    region = (slice(60, 100), slice(96, 136))

    soon = _run(sim, [stopped] * int(1.0 * FPS), start=t)
    t += 1.0
    later = _run(sim, [stopped] * int(25 * FPS), start=t)

    brightness = lambda img: img[region].astype(np.float32).sum(axis=2).mean()  # noqa: E731
    # The same still frame rendered with no heat at all: what "cold" looks like for this object
    # (a bright block reads brighter than the wall even before any warmth is added).
    cold = brightness(simulate_thermal(stopped))
    assert brightness(soon) > 1.5 * cold   # still clearly warm a second after stopping
    assert brightness(later) < 1.15 * cold  # ...and absorbed into the background much later


# --- robustness ----------------------------------------------------------------

def test_a_scene_cut_starts_over_instead_of_lighting_up_the_whole_frame() -> None:
    a, b = _background(1), 255 - _background(2)
    sim = ThermalSimulator()
    _run(sim, [a] * 90)
    out = _run(sim, [b] * 5, start=8.0)  # a completely different scene (e.g. a looping file restarting)

    assert _hot(out).sum() == 0


def test_a_first_frame_timestamp_of_exactly_zero_still_warms_up_and_glows() -> None:
    """Regression: 0.0 is falsy, and treating it as 'no timestamp' kept the
    simulator in its warm-up phase forever, so nothing ever glowed."""
    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75, start=0.0)
    out = _run(sim, [_with_object(bg, x) for x in range(20, 100, 4)], start=75 / FPS)

    assert _hot(out).sum() > 100


def test_nothing_glows_during_the_initial_warm_up() -> None:
    bg = _background()
    sim = ThermalSimulator()
    out = _run(sim, [bg, _with_object(bg, 40), _with_object(bg, 44)], start=5.0)

    assert _hot(out).sum() == 0


def test_reset_forgets_the_learned_scene() -> None:
    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 90)
    sim.reset()
    out = sim.render(_with_object(bg, 60), now=99.0)  # first frame after a reset: just learning

    assert _hot(out).sum() == 0


def test_render_is_deterministic_for_the_same_input_sequence() -> None:
    frames = [_with_object(_background(), x) for x in range(20, 80, 4)]
    a = _run(ThermalSimulator(), frames)
    b = _run(ThermalSimulator(), frames)

    assert np.array_equal(a, b)


def test_output_is_capped_in_width_but_keeps_the_aspect_ratio() -> None:
    big = np.zeros((1080, 1920, 3), np.uint8)
    small = np.zeros((H, W, 3), np.uint8)

    assert ThermalSimulator().render(big, now=1.0).shape == (540, 960, 3)
    assert ThermalSimulator().render(small, now=1.0).shape == (H, W, 3)


def test_a_change_of_frame_size_relearns_instead_of_crashing() -> None:
    sim = ThermalSimulator()
    sim.render(np.zeros((H, W, 3), np.uint8), now=1.0)

    out = sim.render(np.zeros((H * 2, W * 2, 3), np.uint8), now=1.1)

    assert out.shape == (H * 2, W * 2, 3)


def test_irregular_frame_timing_is_handled() -> None:
    bg = _background()
    sim = ThermalSimulator()
    out = None
    for i, t in enumerate([5.0, 5.4, 5.45, 7.0, 7.01, 9.5, 9.6, 12.0]):
        out = sim.render(_with_object(bg, 20 + i * 3) if i > 4 else bg, now=t)

    assert out is not None and out.dtype == np.uint8


# --- stateless fallback -----------------------------------------------------------

def test_the_stateless_fallback_is_dark_deterministic_and_never_glows() -> None:
    frame = _with_object(_background(), 100)

    a, b = simulate_thermal(frame), simulate_thermal(frame.copy())

    assert np.array_equal(a, b)
    assert a.shape == frame.shape
    assert _hot(a).sum() == 0


def test_the_stateless_fallback_caps_the_width_like_the_simulator() -> None:
    assert simulate_thermal(np.zeros((1080, 1920, 3), np.uint8)).shape == (540, 960, 3)


# --- white-hot view for detection -------------------------------------------------

def test_white_hot_view_is_monotonic_with_heat_across_the_whole_palette() -> None:
    from ibvap_common.thermal_sim import _LUT, to_detection_view

    ramp = np.tile(_LUT.reshape(1, 256, 3), (4, 1, 1))  # one column per palette entry, cold -> hot
    grey = to_detection_view(ramp)[0, :, 0].astype(int)

    assert (np.diff(grey) >= -6).all()  # rises (allowing quantisation wobble)
    assert grey[0] < 15 and grey[-1] > 240
    assert grey[128] > grey[40]


def test_white_hot_view_is_a_three_channel_grey_image_of_the_same_size() -> None:
    from ibvap_common.thermal_sim import to_detection_view

    thermal = ThermalSimulator().render(_with_object(_background(), 100), now=1.0)
    view = to_detection_view(thermal)

    assert view.shape == thermal.shape and view.dtype == np.uint8
    assert (view[..., 0] == view[..., 1]).all() and (view[..., 1] == view[..., 2]).all()


def test_an_empty_cold_scene_stays_dark_in_the_white_hot_view() -> None:
    from ibvap_common.thermal_sim import to_detection_view

    out = _run(ThermalSimulator(), [_background()] * 90)

    assert to_detection_view(out).mean() < 90  # not stretched to full brightness


def test_something_hot_is_bright_in_the_white_hot_view() -> None:
    from ibvap_common.thermal_sim import to_detection_view

    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75)
    out = _run(sim, [_with_object(bg, x) for x in range(20, 100, 4)], start=5.0 + 75 / FPS)
    view = to_detection_view(out)[..., 0]

    assert view[_hot(out)].mean() > 170
    assert view[:, 250:].mean() < 90


def test_white_hot_view_survives_jpeg_compression() -> None:
    from ibvap_common.thermal_sim import to_detection_view

    bg = _background()
    sim = ThermalSimulator()
    _run(sim, [bg] * 75)
    out = _run(sim, [_with_object(bg, x) for x in range(20, 100, 4)], start=5.0 + 75 / FPS)
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    round_tripped = cv2.imdecode(enc, cv2.IMREAD_COLOR)  # what detection actually receives

    diff = np.abs(to_detection_view(out).astype(int) - to_detection_view(round_tripped).astype(int))
    assert diff.mean() < 12
