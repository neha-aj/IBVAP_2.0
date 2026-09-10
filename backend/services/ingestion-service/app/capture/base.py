"""Common interface for every capture backend (file, webcam, usb, rtsp, ip).
Everything downstream of this (worker, frame publisher, preview) is written
once against `FrameSource` and never branches on camera type -- adding a new
source type later means adding one more implementation of this class, per
SAS §5.1's addendum for file/webcam sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class FrameSource(ABC):
    """Blocking, synchronous by design -- OpenCV's `VideoCapture` is
    blocking C code. Workers run instances of this inside a thread via
    `asyncio.to_thread` rather than making this class itself async."""

    @abstractmethod
    def open(self) -> bool:
        """Attempts to open the underlying source. Returns True on success."""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Reads the next frame (BGR numpy array), or None if unavailable.
        For looping file sources, returning None never happens on EOF --
        the implementation loops back to the start instead."""

    @abstractmethod
    def release(self) -> None:
        """Releases any underlying OS resources (file handles, devices)."""

    @property
    @abstractmethod
    def declared_fps(self) -> float:
        """The source's nominal FPS (from file metadata or a configured
        target for live devices), used to judge degraded ('warning') status."""

    @property
    def loop_generation(self) -> int:
        """How many times this source has looped back to its start.
        Non-looping sources (webcam/usb/rtsp/ip -- anything that isn't a
        looped file) never override this, so it stays 0 forever for them.
        Downstream (Detection/Tracking/Event-Alert) uses this to recognize
        "this is a replay of footage already counted," so a short looping
        test clip doesn't inflate `peopleDetectedToday` by re-counting the
        same people once per loop."""
        return 0
