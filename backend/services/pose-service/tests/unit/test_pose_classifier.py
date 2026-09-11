from dataclasses import dataclass

from app.inference.pose_classifier import classify_landmarks

# Same eight BlazePose/MediaPipe landmark indices `pose_classifier.py` reads
# -- see that module's own docstring for why these specific indices.
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28


@dataclass(frozen=True)
class FakeLandmark:
    """Plain stand-in for a MediaPipe `NormalizedLandmark` -- only `x`/`y`
    (normalized 0-1) and `visibility` (0-1), the subset `LandmarkLike`
    declares. No real MediaPipe/model dependency needed to build one."""

    x: float
    y: float
    visibility: float = 1.0


def _landmark_set(landmarks: dict[int, FakeLandmark]) -> dict[int, FakeLandmark]:
    return landmarks


def test_standing_pose_classifies_as_standing() -> None:
    """Shoulders directly above hips directly above knees directly above
    ankles -- a textbook upright standing pose: torso vertical (~0 degrees
    from vertical axis), legs straight (~180 degree knee angle)."""
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.45, y=0.2), RIGHT_SHOULDER: FakeLandmark(x=0.55, y=0.2),
        LEFT_HIP: FakeLandmark(x=0.45, y=0.5), RIGHT_HIP: FakeLandmark(x=0.55, y=0.5),
        LEFT_KNEE: FakeLandmark(x=0.45, y=0.75), RIGHT_KNEE: FakeLandmark(x=0.55, y=0.75),
        LEFT_ANKLE: FakeLandmark(x=0.45, y=0.95), RIGHT_ANKLE: FakeLandmark(x=0.55, y=0.95),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert reading.posture == "standing"
    assert reading.confidence == 1.0


def test_walking_midstride_pose_classifies_as_standing_not_sitting() -> None:
    """Reproduces a real false positive found live on this deployment's own
    camera feeds: a normal walking gait has one leg planted (straight) and
    one leg swinging (bent) at any given instant, but was being
    misclassified as 'sitting' because the original classifier used
    min(left, right) knee angle -- any one bent knee was enough to fail the
    straight-leg check, so nearly every walking pedestrian read as
    'sitting'. Right leg here is straight (a planted support leg); left leg
    is sharply bent (mid-swing) -- an upright torso plus a real support leg
    should still read as standing."""
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.45, y=0.2), RIGHT_SHOULDER: FakeLandmark(x=0.55, y=0.2),
        LEFT_HIP: FakeLandmark(x=0.45, y=0.5), RIGHT_HIP: FakeLandmark(x=0.55, y=0.5),
        LEFT_KNEE: FakeLandmark(x=0.55, y=0.65), RIGHT_KNEE: FakeLandmark(x=0.55, y=0.75),
        LEFT_ANKLE: FakeLandmark(x=0.45, y=0.7), RIGHT_ANKLE: FakeLandmark(x=0.55, y=0.95),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert reading.posture == "standing"


def test_seated_pose_classifies_as_sitting() -> None:
    """Upright torso, but the knee juts forward of the hip-ankle line at the
    same height as the hip -- a textbook seated pose (e.g. on a chair):
    torso still reads vertical, but the hip-knee-ankle angle is a sharp
    bend, not a straight leg."""
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.45, y=0.2), RIGHT_SHOULDER: FakeLandmark(x=0.55, y=0.2),
        LEFT_HIP: FakeLandmark(x=0.45, y=0.5), RIGHT_HIP: FakeLandmark(x=0.55, y=0.5),
        LEFT_KNEE: FakeLandmark(x=0.65, y=0.5), RIGHT_KNEE: FakeLandmark(x=0.75, y=0.5),
        LEFT_ANKLE: FakeLandmark(x=0.65, y=0.75), RIGHT_ANKLE: FakeLandmark(x=0.75, y=0.75),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert reading.posture == "sitting"


def test_lying_pose_classifies_as_sleeping() -> None:
    """Shoulders and hips at (roughly) the same height, side by side --
    torso reads as horizontal (~90 degrees from vertical), the strongest
    signal for lying down regardless of leg bend."""
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.2, y=0.5), RIGHT_SHOULDER: FakeLandmark(x=0.2, y=0.55),
        LEFT_HIP: FakeLandmark(x=0.5, y=0.5), RIGHT_HIP: FakeLandmark(x=0.5, y=0.55),
        LEFT_KNEE: FakeLandmark(x=0.7, y=0.5), RIGHT_KNEE: FakeLandmark(x=0.7, y=0.55),
        LEFT_ANKLE: FakeLandmark(x=0.9, y=0.5), RIGHT_ANKLE: FakeLandmark(x=0.9, y=0.55),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert reading.posture == "sleeping"


def test_bent_torso_moderate_lean_classifies_as_sitting_not_standing() -> None:
    """A torso tilted enough to fail the 'standing' straight-vertical bar
    but nowhere near horizontal, combined with straight legs, is exactly
    the ambiguous middle case this module's docstring says should fall
    through to the 'sitting' catch-all rather than 'standing'."""
    # Shoulder-mid (0.2, 0.2) to hip-mid (0.5, 0.5): dx=0.3, dy=0.3 -> a 45
    # degree torso lean, comfortably between `torso_vertical_max_degrees`
    # (35) and `torso_horizontal_min_degrees` (60). Legs stay straight
    # (hip/knee/ankle share the same x per side) so only the torso angle
    # is what keeps this out of "standing".
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.15, y=0.2), RIGHT_SHOULDER: FakeLandmark(x=0.25, y=0.2),
        LEFT_HIP: FakeLandmark(x=0.45, y=0.5), RIGHT_HIP: FakeLandmark(x=0.55, y=0.5),
        LEFT_KNEE: FakeLandmark(x=0.45, y=0.75), RIGHT_KNEE: FakeLandmark(x=0.55, y=0.75),
        LEFT_ANKLE: FakeLandmark(x=0.45, y=0.95), RIGHT_ANKLE: FakeLandmark(x=0.55, y=0.95),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert reading.posture == "sitting"


def test_missing_required_landmark_returns_none() -> None:
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.45, y=0.2), RIGHT_SHOULDER: FakeLandmark(x=0.55, y=0.2),
        LEFT_HIP: FakeLandmark(x=0.45, y=0.5), RIGHT_HIP: FakeLandmark(x=0.55, y=0.5),
        # knees/ankles missing entirely (e.g. legs out of frame)
    })

    assert classify_landmarks(landmarks) is None


def test_low_visibility_landmarks_lower_confidence() -> None:
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.45, y=0.2, visibility=0.3),
        RIGHT_SHOULDER: FakeLandmark(x=0.55, y=0.2, visibility=0.3),
        LEFT_HIP: FakeLandmark(x=0.45, y=0.5, visibility=0.3),
        RIGHT_HIP: FakeLandmark(x=0.55, y=0.5, visibility=0.3),
        LEFT_KNEE: FakeLandmark(x=0.45, y=0.75, visibility=0.3),
        RIGHT_KNEE: FakeLandmark(x=0.55, y=0.75, visibility=0.3),
        LEFT_ANKLE: FakeLandmark(x=0.45, y=0.95, visibility=0.3),
        RIGHT_ANKLE: FakeLandmark(x=0.55, y=0.95, visibility=0.3),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert reading.confidence == 0.3


def test_center_point_is_percentage_of_frame() -> None:
    landmarks = _landmark_set({
        LEFT_SHOULDER: FakeLandmark(x=0.4, y=0.2), RIGHT_SHOULDER: FakeLandmark(x=0.6, y=0.2),
        LEFT_HIP: FakeLandmark(x=0.4, y=0.5), RIGHT_HIP: FakeLandmark(x=0.6, y=0.5),
        LEFT_KNEE: FakeLandmark(x=0.4, y=0.75), RIGHT_KNEE: FakeLandmark(x=0.6, y=0.75),
        LEFT_ANKLE: FakeLandmark(x=0.4, y=0.95), RIGHT_ANKLE: FakeLandmark(x=0.6, y=0.95),
    })

    reading = classify_landmarks(landmarks)

    assert reading is not None
    assert 0.0 <= reading.x <= 100.0
    assert 0.0 <= reading.y <= 100.0
    # bbox center of x in [0.4, 0.6] -> 50%; y in [0.2, 0.95] -> 57.5%
    assert reading.x == 50.0
    assert abs(reading.y - 57.5) < 1e-6
