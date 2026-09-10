"""Dwell-time rule (SAS §5.4.2: "dwell time over threshold -> 'Loitering
Detected'"). Pure -- the engine owns "already fired for this track"
bookkeeping."""

from __future__ import annotations

import datetime as dt


def has_exceeded_dwell_time(first_seen: dt.datetime, now: dt.datetime, *, threshold_seconds: int) -> bool:
    return (now - first_seen).total_seconds() >= threshold_seconds
