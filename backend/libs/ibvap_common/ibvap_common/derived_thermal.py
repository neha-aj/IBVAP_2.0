"""Marker for a camera whose thermal view is rendered from its own RGB video
rather than read from a separate thermal source (see `thermal_sim`).

Kept apart from `thermal_sim` on purpose: services that only need to *recognise*
the marker (camera-service) must not have to import OpenCV.
"""

from __future__ import annotations

# Stored in a camera's `thermal_source_url` to mean "no separate thermal file
# -- render it from this camera's own RGB video". Never a real path.
DERIVED_THERMAL_SOURCE = "derived:rgb"


def is_derived_thermal(thermal_source_url: str | None) -> bool:
    return thermal_source_url == DERIVED_THERMAL_SOURCE
