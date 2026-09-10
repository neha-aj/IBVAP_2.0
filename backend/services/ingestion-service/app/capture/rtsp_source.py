"""RTSP/ONVIF network camera capture via OpenCV's FFmpeg backend. Not
exercised in this phase (no real cameras available yet per the user), but
implemented against the same `FrameSource` interface so onboarding real
hardware later requires zero changes anywhere else in the pipeline."""

from __future__ import annotations

import cv2
import numpy as np

from app.capture.base import FrameSource


class RtspFrameSource(FrameSource):
    def __init__(self, rtsp_url: str, *, target_fps: float = 25.0) -> None:
        self._url = rtsp_url
        self._target_fps = target_fps
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        return self._cap.isOpened()

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def declared_fps(self) -> float:
        if self._cap is None:
            return self._target_fps
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        return fps if fps and fps > 0 else self._target_fps
