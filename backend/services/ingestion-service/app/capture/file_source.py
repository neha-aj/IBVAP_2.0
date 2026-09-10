"""Reads an uploaded video file frame-by-frame, looping back to the start on
end-of-stream so it behaves like a continuous camera feed. This is the
primary way to develop/demo IBVAP without any real hardware (per the user's
"any source video I insert" requirement)."""

from __future__ import annotations

import cv2
import numpy as np

from app.capture.base import FrameSource


class FileFrameSource(FrameSource):
    def __init__(self, file_path: str, *, loop: bool = True, initial_generation: int = 0) -> None:
        self._path = file_path
        self._loop = loop
        self._cap: cv2.VideoCapture | None = None
        # Seeded from Redis by CameraWorker so a worker restart (crash,
        # redeploy, host reboot) resumes the count instead of looking like a
        # brand new first play-through -- otherwise every restart would
        # re-count this file's people/vehicles as "new" for the day.
        self._loop_generation = initial_generation

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._path)
        return self._cap.isOpened()

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok:
            if self._loop:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._cap.read()
                if not ok:
                    return None
                self._loop_generation += 1
            else:
                return None
        return frame

    @property
    def loop_generation(self) -> int:
        return self._loop_generation

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def declared_fps(self) -> float:
        if self._cap is None:
            return 0.0
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        return fps if fps and fps > 0 else 25.0
