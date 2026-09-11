"""Thin wrapper around MediaPipe Tasks API's `PoseLandmarker` -- the actual
trained model this service runs (CPU, no GPU needed; see the module
docstring on `pose_classifier.py` for why a separate person detector isn't
needed: `num_poses` makes it multi-person-native). This module owns
model loading and the MediaPipe-specific `Image`/`PoseLandmarkerResult`
shapes; `pose_classifier.classify_landmarks` (pure geometry, no MediaPipe
import) does the actual posture classification so that function stays
unit-testable without a real model file or real image processing."""

from __future__ import annotations

import numpy as np

from app.inference.pose_classifier import classify_landmarks
from app.schemas.pose import PoseReading


class PoseLandmarkerModel:
    """Loads the MediaPipe `PoseLandmarker` Tasks-API model once (expensive)
    and exposes a simple `(bgr_frame) -> list[PoseReading]` call, mirroring
    the `(frame) -> float` injectable-scorer shape fire-smoke-service's
    `heuristics.py` functions use -- except here the "score function" is a
    stateful object because a real model needs to be loaded once, not a
    pure function."""

    def __init__(
        self,
        *,
        model_path: str,
        max_poses: int,
        min_pose_confidence: float,
        torso_vertical_max_degrees: float,
        torso_horizontal_min_degrees: float,
        knee_bend_max_degrees: float,
    ) -> None:
        # Imported lazily so importing this module (e.g. from
        # `pose_service.py` for type hints, or from test collection) never
        # requires the `mediapipe` package / a real model file to be
        # present unless a `PoseLandmarkerModel` is actually constructed --
        # same reasoning as keeping `classify_landmarks` mediapipe-free.
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode

        self._mp = mp
        self._min_pose_confidence = min_pose_confidence
        self._torso_vertical_max_degrees = torso_vertical_max_degrees
        self._torso_horizontal_min_degrees = torso_horizontal_min_degrees
        self._knee_bend_max_degrees = knee_bend_max_degrees

        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionTaskRunningMode.IMAGE,  # one independent call per sampled frame, no video tracking state
            num_poses=max_poses,
            min_pose_detection_confidence=min_pose_confidence,
            min_pose_presence_confidence=min_pose_confidence,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def detect(self, bgr_frame: np.ndarray) -> list[PoseReading]:
        rgb_frame = bgr_frame[:, :, ::-1]  # MediaPipe expects RGB, frames arrive as BGR (cv2 convention)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb_frame))
        result = self._landmarker.detect(mp_image)

        readings: list[PoseReading] = []
        for pose_landmarks in result.pose_landmarks:
            landmarks = {i: lm for i, lm in enumerate(pose_landmarks)}
            reading = classify_landmarks(
                landmarks,
                torso_vertical_max_degrees=self._torso_vertical_max_degrees,
                torso_horizontal_min_degrees=self._torso_horizontal_min_degrees,
                knee_bend_max_degrees=self._knee_bend_max_degrees,
            )
            if reading is not None and reading.confidence >= self._min_pose_confidence:
                readings.append(reading)
        return readings

    def close(self) -> None:
        self._landmarker.close()
