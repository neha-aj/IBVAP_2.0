"""Direction Analysis rule (Phase 2 doc09 §1.2): a moving average of a
track's recent centroid displacement vectors, bucketed into one of 8
compass directions. Pure -- the engine owns the recent-positions history
per track.

Compass convention: frame coordinates have y increasing *downward*, and
there's no real-world compass reference for an arbitrary camera's framing,
so "N" is defined here as "up the frame" (decreasing y) purely as a fixed,
documented convention -- consistent across every camera, not a claim about
true geographic north.
"""

from __future__ import annotations

import math

from app.schemas.internal import Point

_DIRECTIONS = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]

# Plain-language phrasing for each compass bucket, for the human-facing
# `description` text only -- the stored `direction` column stays the raw
# compass code above, since that's what `mv_direction_flow` groups by and
# a plain phrase isn't a stable enough key for that. "N"/"S" here mean
# "up"/"down the frame" per this module's own compass convention, not a
# real-world heading.
_PLAIN_LANGUAGE = {
    "N": "moving toward the top of the frame",
    "S": "moving toward the bottom of the frame",
    "E": "moving right",
    "W": "moving left",
    "NE": "moving up and to the right",
    "NW": "moving up and to the left",
    "SE": "moving down and to the right",
    "SW": "moving down and to the left",
}


def describe(bucket: str) -> str:
    return _PLAIN_LANGUAGE.get(bucket, bucket)


def average_heading(positions: list[Point]) -> tuple[float, float] | None:
    """Average displacement vector across consecutive pairs in `positions`
    (oldest first). None if there's fewer than two positions to derive a
    displacement from at all."""
    if len(positions) < 2:
        return None
    dxs = [positions[i + 1].x - positions[i].x for i in range(len(positions) - 1)]
    dys = [positions[i + 1].y - positions[i].y for i in range(len(positions) - 1)]
    return sum(dxs) / len(dxs), sum(dys) / len(dys)


def compass_bucket(dx: float, dy: float) -> str:
    if dx == 0 and dy == 0:
        return "N"  # stationary reading -- arbitrary but fixed default
    angle = math.degrees(math.atan2(-dy, dx)) % 360
    index = round(angle / 45) % 8
    return _DIRECTIONS[index]
