"""Local capture device (laptop/USB webcam) via OpenCV's device-index API.
Also used for `usb`-type cameras -- identical mechanics, different intent."""

from __future__ import annotations

import cv2
import numpy as np

from app.capture.base import FrameSource


class WebcamFrameSource(FrameSource):
    def __init__(self, device: str, *, target_fps: float = 25.0) -> None:
        # `device` is typically a small integer index ("0", "1", ...) as a
        # string, matching the `sourceUrl` the frontend/API stores; also
        # accepts a device path (e.g. "/dev/video0") on Linux.
        self._device = device
        self._target_fps = target_fps
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        index_or_path: int | str = int(self._device) if self._device.isdigit() else self._device
        self._cap = cv2.VideoCapture(index_or_path)
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
