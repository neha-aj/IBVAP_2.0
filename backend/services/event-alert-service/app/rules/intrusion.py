"""Zone-crossing/intrusion rule (SAS §5.4.2: "simple zone-crossing (if a
zone polygon is configured) -> 'Fence Intrusion'/'Restricted Zone Entry'").
Pure and stateless -- the engine owns "has this track already been flagged
for this zone" bookkeeping so this stays trivially testable."""

from __future__ import annotations

from app.rules.zone_crossing import bbox_center, point_in_polygon
from app.schemas.internal import BoundingBox, Zone

# `general` zones are scaffolded for future capabilities (SAS §5.4.3 dwell
# time/zone occupancy) but aren't alert-worthy on their own.
_ALERTABLE_ZONE_LABELS = {"perimeter": "Fence Intrusion", "restricted": "Restricted Zone Entry"}
_ALERTABLE_ZONE_SEVERITY = {"perimeter": "critical", "restricted": "high"}


def find_matching_zone(bbox: BoundingBox, zones: list[Zone]) -> Zone | None:
    """Returns the first alertable zone (perimeter/restricted) whose polygon
    contains this track's bbox center, or None."""
    cx, cy = bbox_center(bbox)
    for zone in zones:
        if zone.zone_type not in _ALERTABLE_ZONE_LABELS:
            continue
        if point_in_polygon(cx, cy, zone.polygon):
            return zone
    return None


def event_label_for_zone(zone: Zone) -> str:
    return _ALERTABLE_ZONE_LABELS[zone.zone_type]


def severity_for_zone(zone: Zone) -> str:
    return _ALERTABLE_ZONE_SEVERITY[zone.zone_type]
