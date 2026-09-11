"""Abandoned Object Detection (behavioral analytics): same dwell-time shape
as `loitering.py` (`has_exceeded_dwell_time` is reused directly, unmodified,
for the "how long has this bag been sitting there" half of the check), plus
a companion "is anyone still with it" check `loitering.py` doesn't need --
a bag someone is sitting beside for 5 minutes isn't abandoned, it's just
someone's bag."""

from __future__ import annotations

from app.schemas.internal import BoundingBox


def _center(bbox: BoundingBox) -> tuple[float, float]:
    return bbox.x + bbox.width / 2, bbox.y + bbox.height / 2


def is_unattended(bag_bbox: BoundingBox, person_bboxes: list[BoundingBox], *, proximity_threshold: float) -> bool:
    """True if no currently-active person's last-known bbox center is
    within `proximity_threshold` (same percentage-of-frame units as every
    other distance check in this codebase) of the bag's."""
    bx, by = _center(bag_bbox)
    for person_bbox in person_bboxes:
        px, py = _center(person_bbox)
        if ((bx - px) ** 2 + (by - py) ** 2) ** 0.5 <= proximity_threshold:
            return False
    return True
