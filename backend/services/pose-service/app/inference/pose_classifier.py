"""Posture classification -- a real geometric classifier (joint-angle math)
on top of a real trained pose-estimation model (MediaPipe's Tasks API
`PoseLandmarker`, a BlazePose-based model trained on a large annotated
human-pose dataset), not the pure color/shape heuristics the rest of this
codebase uses for fire-smoke-service/tamper-service (see
`fire-smoke-service/app/inference/heuristics.py`'s own docstring for that
contrast). `PoseLandmarker` itself does the hard part -- finding each
person and their 33 body-joint keypoints in the frame, including the
multi-person case natively via its `num_poses` option, so this service
needs no separate person detector. What lives in *this* module is only the
next step: turning one person's 33 landmarks into a standing/sitting/
sleeping label using real, standard body-pose geometry.

**Method** (per detected pose):

1. Torso-vertical angle: the angle between the shoulder-midpoint ->
   hip-midpoint vector and the image's vertical (gravity) axis. Near 0
   degrees means an upright torso; near 90 degrees means a horizontal
   (lying-down) torso.
2. Hip-knee-ankle bend angle: the interior angle at the knee joint between
   the knee->hip and knee->ancle vectors. Near 180 degrees means a
   straight leg (standing); a meaningfully smaller angle means a bent knee
   (seated).
3. Classification, in priority order:
   - Torso angle >= `torso_horizontal_min_degrees` -> **sleeping**. A
     near-horizontal torso is the single strongest, most direct signal for
     "lying down" of the three postures -- checked first so a person lying
     on the ground with one leg bent (common when lying on one's side)
     isn't misread as seated just because the leg-angle check would have
     said "bent."
   - Torso angle <= `torso_vertical_max_degrees` AND legs straight (knee
     angle >= `knee_bend_max_degrees`) -> **standing**.
   - Otherwise -> **sitting**. This is deliberately the catch-all: an
     upright-to-moderately-tilted torso combined with a bent knee (the
     textbook seated posture) lands here, but so does anything in between
     that clears neither of the other two bars -- which is the right
     default, since "ambiguous, non-prone, non-fully-upright-straight-leg"
     is a much closer real-world match to "sitting" than to either
     alternative.

Confidence is the mean MediaPipe landmark `visibility` (0-1, the model's
own estimate of whether the joint is actually visible/unoccluded in frame)
across the eight joints used for classification -- a genuine model-reported
number, not fabricated.

**This is meaningfully more reliable than fire-smoke-service's color-only
heuristics** -- it's built on an actual trained keypoint model, not raw
pixel color/texture -- but it is still a geometric approximation, not a
validated posture classifier, and has real, disclosed failure modes:

- **Crouching/kneeling** can land on either "sitting" or "standing"
  depending on exact torso lean and how bent the knee reads -- there's no
  fourth "crouching" bucket in this system's contract (standing/sitting/
  sleeping only), so crouching is inherently forced into the nearest of
  the three, and which one it lands on is genuinely ambiguous geometry,
  not a bug.
- **Lying on one's side facing the camera** can be ambiguous with sitting
  from some camera angles: if the camera views the scene from close to
  along the body's own long axis, the projected shoulder-hip vector in
  the 2D image can read as more vertical than the person's true (3D)
  horizontal orientation, understating the torso angle. MediaPipe's
  landmarks do carry a `z` (depth) coordinate that could disambiguate this
  in a future iteration; this module deliberately uses only 2D image-plane
  geometry for now, matching the "vs. the vertical/gravity axis of the
  image" framing this was scoped to.
- **Partial occlusion** (e.g. legs out of frame or behind an obstacle)
  lowers the visibility/confidence of the knee/ankle landmarks used for
  the leg-straightness check; a low-confidence reading is still returned
  (the caller applies `Settings.min_pose_confidence` as the drop
  threshold, not this module), but the underlying geometric read is less
  trustworthy the more of the body is occluded.
- **Non-canonical poses** (e.g. a handstand, or someone bent fully over at
  the waist while standing) aren't in the training/geometric assumptions
  behind "torso vertical = standing" and can misclassify.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.schemas.pose import Posture, PoseReading

# BlazePose / MediaPipe PoseLandmarker's fixed 33-landmark topology --
# https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
# (indices are part of the model's published contract, not arbitrary).
_LEFT_SHOULDER, _RIGHT_SHOULDER = 11, 12
_LEFT_HIP, _RIGHT_HIP = 23, 24
_LEFT_KNEE, _RIGHT_KNEE = 25, 26
_LEFT_ANKLE, _RIGHT_ANKLE = 27, 28

_REQUIRED_INDICES = (
    _LEFT_SHOULDER, _RIGHT_SHOULDER, _LEFT_HIP, _RIGHT_HIP,
    _LEFT_KNEE, _RIGHT_KNEE, _LEFT_ANKLE, _RIGHT_ANKLE,
)


class LandmarkLike(Protocol):
    """The subset of a MediaPipe `NormalizedLandmark` this module reads --
    `x`/`y` normalized 0-1 relative to frame width/height, `visibility`
    0-1. Declared as a `Protocol` (structural typing) rather than importing
    MediaPipe's own landmark class here so `classify_landmarks` stays
    testable with plain objects/namedtuples (see
    `tests/unit/test_pose_classifier.py`), the same "injectable, real-model-
    independent geometry" split fire-smoke-service's own
    `heuristics.py`/`fire_smoke_service.py` use."""

    x: float
    y: float
    visibility: float


@dataclass(frozen=True)
class _Point:
    x: float
    y: float


def _midpoint(a: LandmarkLike, b: LandmarkLike) -> _Point:
    return _Point((a.x + b.x) / 2, (a.y + b.y) / 2)


def _angle_from_vertical_degrees(top: _Point, bottom: _Point) -> float:
    """Angle, in degrees, between the vector `top -> bottom` and the image's
    vertical (gravity) axis (0,1) -- image y increases downward, so a
    person standing perfectly upright has `bottom` directly below `top`
    and this returns ~0."""
    dx, dy = bottom.x - top.x, bottom.y - top.y
    magnitude = math.hypot(dx, dy)
    if magnitude == 0:
        return 0.0
    # cos(theta) = (vector . vertical_axis) / |vector| ; vertical_axis=(0,1)
    cos_theta = max(-1.0, min(1.0, dy / magnitude))
    return math.degrees(math.acos(cos_theta))


def _joint_angle_degrees(vertex: LandmarkLike, a: LandmarkLike, b: LandmarkLike) -> float:
    """Interior angle at `vertex`, in degrees, between rays `vertex->a` and
    `vertex->b` -- used for the hip-knee-ankle bend angle (`vertex`=knee,
    `a`=hip, `b`=ankle). ~180 degrees is a straight leg."""
    v1 = (a.x - vertex.x, a.y - vertex.y)
    v2 = (b.x - vertex.x, b.y - vertex.y)
    mag1, mag2 = math.hypot(*v1), math.hypot(*v2)
    if mag1 == 0 or mag2 == 0:
        return 180.0  # degenerate (coincident points) -- treat as "straight", not "bent"
    cos_theta = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)))
    return math.degrees(math.acos(cos_theta))


def classify_landmarks(
    landmarks: dict[int, LandmarkLike],
    *,
    torso_vertical_max_degrees: float = 35.0,
    torso_horizontal_min_degrees: float = 60.0,
    knee_bend_max_degrees: float = 155.0,
) -> PoseReading | None:
    """Pure geometry: turns one person's landmark set into a `PoseReading`,
    with no MediaPipe/image dependency -- the injectable core this module's
    docstring describes, unit-tested directly with synthetic landmark dicts
    rather than real images/model inference. Returns `None` if any of the
    eight joints this classification needs (shoulders/hips/knees/ankles)
    is missing from `landmarks` (e.g. a caller pre-filtered low-visibility
    joints out)."""
    if not all(i in landmarks for i in _REQUIRED_INDICES):
        return None

    left_shoulder, right_shoulder = landmarks[_LEFT_SHOULDER], landmarks[_RIGHT_SHOULDER]
    left_hip, right_hip = landmarks[_LEFT_HIP], landmarks[_RIGHT_HIP]
    left_knee, right_knee = landmarks[_LEFT_KNEE], landmarks[_RIGHT_KNEE]
    left_ankle, right_ankle = landmarks[_LEFT_ANKLE], landmarks[_RIGHT_ANKLE]

    shoulder_mid = _midpoint(left_shoulder, right_shoulder)
    hip_mid = _midpoint(left_hip, right_hip)
    torso_angle = _angle_from_vertical_degrees(shoulder_mid, hip_mid)

    left_knee_angle = _joint_angle_degrees(left_knee, left_hip, left_ankle)
    right_knee_angle = _joint_angle_degrees(right_knee, right_hip, right_ankle)
    # max(), not min(): a normal walking gait has one leg swinging (bent,
    # sometimes well under 155 degrees) while the other is the planted
    # support leg (straight) -- live-tested against this deployment's real
    # camera feeds and confirmed this was misclassifying most walking
    # pedestrians as "sitting" under the original min() (any one bent knee
    # forced "bent"). A standing/walking person always has at least one
    # straight leg at any given instant; a seated person has neither (see
    # `test_seated_pose_classifies_as_sitting`, where both knees are bent
    # symmetrically and max() still correctly reads "bent").
    knee_angle = max(left_knee_angle, right_knee_angle)

    posture: Posture
    if torso_angle >= torso_horizontal_min_degrees:
        posture = "sleeping"
    elif torso_angle <= torso_vertical_max_degrees and knee_angle >= knee_bend_max_degrees:
        posture = "standing"
    else:
        posture = "sitting"

    relevant = (
        left_shoulder, right_shoulder, left_hip, right_hip,
        left_knee, right_knee, left_ankle, right_ankle,
    )
    confidence = sum(max(0.0, min(1.0, lm.visibility)) for lm in relevant) / len(relevant)

    # Center point: bounding-box center of the eight joints used for
    # classification, as a 0-100 percentage of frame width/height --
    # matches detection-service's `BoundingBox` percentage convention
    # (`app/schemas/detection.py`) so the frontend can distance-match this
    # against a `person` detection box's own center.
    xs = [lm.x for lm in relevant]
    ys = [lm.y for lm in relevant]
    center_x = (min(xs) + max(xs)) / 2 * 100
    center_y = (min(ys) + max(ys)) / 2 * 100

    return PoseReading(
        x=max(0.0, min(100.0, center_x)),
        y=max(0.0, min(100.0, center_y)),
        posture=posture,
        confidence=round(confidence, 4),
    )
