"""Orchestrates the Phase-1 rule set (SAS §5.4.2) against incoming track
lifecycle events and camera status changes. Owns all the per-camera/
per-track "has this already fired" state so the individual rule modules
(`intrusion`, `loitering`, `offline_alert`) can stay pure functions.

Person/vehicle count thresholds don't get their own file in the documented
project structure (`rules/{intrusion.py,loitering.py,offline_alert.py,
zone_crossing.py}`) -- they're simple enough to live directly here as the
engine's own active-count bookkeeping.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.repositories.track_repo import TrackRepository
from app.rules import (
    abandoned_object, direction, fighting, intrusion, line_crossing, loitering, offline_alert, speed, zone_crossing,
)
from app.schemas.internal import BoundingBox, CameraInfo, Point, TrackEvent, Zone, ZoneLine

ZoneProvider = Callable[[str], Awaitable[list[Zone]]]
ZoneLineProvider = Callable[[str], Awaitable[list[ZoneLine]]]
CameraInfoProvider = Callable[[str], Awaitable[CameraInfo]]


@dataclass
class EventDraft:
    """What a rule firing needs to become an `events` row (and, if
    `requires_review`, a linked `alerts` row too) -- camera name/location
    are filled in by whoever persists this, not the rule engine itself."""

    camera_id: str
    event_type: str
    object_type: str | None
    severity: str
    description: str | None
    requires_review: bool
    # Phase 2 M14 Direction Analysis only -- one of 8 compass buckets, set
    # exclusively on "Direction Observed" drafts (see models/event.py's
    # `direction` column docstring for why this stays a DB-only field).
    direction: str | None = None


@dataclass
class _LostTrack:
    """A just-lost track's last known position, kept around briefly so the
    merge heuristic can recognize its owner reappearing nearby."""

    track_ref: str
    object_type: str
    bbox: BoundingBox
    lost_at: dt.datetime


async def _empty_zone_lines() -> list[ZoneLine]:
    return []


def _bbox_center_distance(a: BoundingBox, b: BoundingBox) -> float:
    """Euclidean distance between two bbox centers, in the same
    percentage-of-frame units the tracker already reports boxes in."""
    ax, ay = a.x + a.width / 2, a.y + a.height / 2
    bx, by = b.x + b.width / 2, b.y + b.height / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


class RuleEngine:
    def __init__(
        self, settings: Settings, zone_provider: ZoneProvider, zone_line_provider: ZoneLineProvider | None = None,
        camera_info_provider: CameraInfoProvider | None = None,
    ) -> None:
        self._settings = settings
        self._zone_provider = zone_provider
        # Optional (defaults to "no lines configured anywhere") so existing
        # callers/tests that only care about polygon zones don't need to
        # know Line Crossing (M13) exists.
        self._zone_line_provider: ZoneLineProvider = zone_line_provider or (lambda camera_id: _empty_zone_lines())
        self._camera_info_provider = camera_info_provider
        self._active_counts: dict[str, dict[str, set[str]]] = {}
        self._count_alert_active: dict[tuple[str, str], bool] = {}
        self._loitering_fired: set[tuple[str, str]] = set()
        self._zone_state: dict[tuple[str, str], str | None] = {}
        # Zone Entry/Exit (M13) -- deliberately separate from `_zone_state`
        # above (intrusion's own bookkeeping, restricted/perimeter only):
        # `find_general_zone` only ever matches `general` zones, so a track
        # can independently be "inside" one of each kind at once.
        self._general_zone_state: dict[tuple[str, str], str | None] = {}
        # Line Crossing/Wrong-Way/Speed Estimation (M13/M14) all need the
        # *previous* centroid (+ its timestamp, for speed) to test against
        # the current one -- keyed the same way as everything else here,
        # per (camera_id, resolved_track_ref).
        self._last_centroid: dict[tuple[str, str], Point] = {}
        self._last_centroid_time: dict[tuple[str, str], dt.datetime] = {}
        # Direction Analysis (M14): last N centroids per track (oldest
        # first), and when a "Direction Observed" row was last emitted for
        # it -- emitting on literally every track update would flood the
        # events table with an entry every ~100ms per track.
        self._heading_history: dict[tuple[str, str], list[Point]] = {}
        self._direction_last_emitted: dict[tuple[str, str], dt.datetime] = {}
        # Crowd Density (M14): which density-configured zones each track was
        # last known to be inside (a track can count toward several at
        # once), plus the resulting per-zone occupancy sets and "already
        # over threshold" debounce -- same shape as `_count_alert_active`.
        self._track_density_zones: dict[tuple[str, str], set[str]] = {}
        self._zone_occupancy: dict[tuple[str, str], set[str]] = {}
        self._density_alert_active: dict[tuple[str, str], bool] = {}
        # Track-merge heuristic state (Settings.enable_track_merge) -- maps
        # a raw incoming track_id to the canonical track_ref it was merged
        # into, remembers each canonical ref's last known position, and
        # keeps a short-lived list of just-lost tracks per camera to match
        # new sightings against.
        self._alias: dict[tuple[str, str], str] = {}
        self._last_bbox: dict[tuple[str, str], BoundingBox] = {}
        self._recently_lost: dict[str, list[_LostTrack]] = {}
        # Behavioral analytics: Fighting Detection needs each *person*
        # track's last bbox (for pairwise proximity, cheaper than re-scanning
        # `_last_bbox` and filtering by type) and a short rolling history of
        # its per-update displacement magnitude (see `rules/fighting.py`).
        # Abandoned Object Detection reuses the same last-person-bbox map for
        # its "is anyone still with this bag" check.
        self._person_last_bbox: dict[tuple[str, str], BoundingBox] = {}
        self._displacement_history: dict[tuple[str, str], list[float]] = {}
        self._fighting_fired: set[tuple[str, frozenset[str]]] = set()
        self._abandoned_fired: set[tuple[str, str]] = set()

    async def handle_track_event(
        self, event: TrackEvent, track_repo: TrackRepository, now: dt.datetime
    ) -> list[EventDraft]:
        drafts: list[EventDraft] = []
        # `defaultdict` (not a plain {"person":..., "vehicle":...} literal)
        # so any object_type -- "animal" (M21), and now "bag" (Abandoned
        # Object Detection) -- can be counted without a KeyError; only
        # person/vehicle ever feed `_check_count_threshold` below, so this
        # is purely a safety net for the others, not a behavior change for
        # either of those two.
        counts = self._active_counts.setdefault(event.camera_id, defaultdict(set))
        # Count-threshold rule cares about "how many distinct ByteTrack ids
        # are in frame right now" -- unaffected by loop_generation or the
        # merge heuristic below, both of which only change what gets
        # persisted/counted for analytics, not this live presence check.
        resolved_ref = event.track_id

        if event.event == "track.started":
            counts[event.object_type].add(event.track_id)

            merged = None
            if self._settings.enable_track_merge and event.bbox is not None:
                merged = self._pop_merge_candidate(event.camera_id, event.object_type, event.bbox, now)

            if merged is not None:
                resolved_ref = merged.track_ref
                self._alias[(event.camera_id, event.track_id)] = resolved_ref
                track = await track_repo.get_by_ref(event.camera_id, resolved_ref)
                if track is not None:
                    await track_repo.reactivate(track, now)
                else:
                    # Shouldn't happen (the ref just came from a lost-track
                    # record), but fall back to starting fresh rather than
                    # dropping the sighting.
                    await track_repo.start(
                        camera_id=event.camera_id, track_ref=resolved_ref, object_type=event.object_type,
                        now=now, loop_generation=event.loop_generation,
                    )
            else:
                # A redelivered `track.started` (at-least-once processing,
                # SAS §11 -- e.g. unacked entries reprocessed after a
                # restart) for a ref that's already active must not fork a
                # second row for the same physical track; treat it as a
                # touch instead.
                existing = await track_repo.get_active(event.camera_id, event.track_id)
                if existing is not None:
                    await track_repo.touch(existing, now)
                else:
                    await track_repo.start(
                        camera_id=event.camera_id, track_ref=event.track_id, object_type=event.object_type, now=now,
                        loop_generation=event.loop_generation,
                    )

            if event.bbox is not None:
                self._last_bbox[(event.camera_id, resolved_ref)] = event.bbox

        elif event.event == "track.updated":
            counts[event.object_type].add(event.track_id)  # self-heals if we missed the .started (e.g. restart)
            resolved_ref = self._alias.get((event.camera_id, event.track_id), event.track_id)
            if event.bbox is not None:
                self._last_bbox[(event.camera_id, resolved_ref)] = event.bbox

            track = await track_repo.get_active(event.camera_id, resolved_ref)
            if track is not None:
                await track_repo.touch(track, now)
                key = (event.camera_id, resolved_ref)
                if key not in self._loitering_fired and loitering.has_exceeded_dwell_time(
                    track.first_seen, now, threshold_seconds=self._settings.loitering_seconds_threshold
                ):
                    self._loitering_fired.add(key)
                    drafts.append(
                        EventDraft(
                            camera_id=event.camera_id,
                            event_type="Loitering Detected",
                            object_type=event.object_type,
                            severity="medium",
                            description=f"Object present for over {self._settings.loitering_seconds_threshold}s",
                            requires_review=True,
                        )
                    )

                # Abandoned Object Detection (behavioral analytics): its own,
                # longer dwell threshold than generic Loitering above -- both
                # can fire for the same bag (Loitering at 30s, this at 180s
                # by default), which is expected, not a conflict: Loitering
                # is generic "something's been still a while", this is the
                # specific "nobody's with this bag" alert. See
                # `rules/abandoned_object.py`.
                if (
                    event.object_type == "bag" and event.bbox is not None and key not in self._abandoned_fired
                    and loitering.has_exceeded_dwell_time(
                        track.first_seen, now, threshold_seconds=self._settings.abandoned_object_seconds_threshold
                    )
                ):
                    nearby_people = [
                        bbox for (cam_id, _ref), bbox in self._person_last_bbox.items() if cam_id == event.camera_id
                    ]
                    if abandoned_object.is_unattended(
                        event.bbox, nearby_people,
                        proximity_threshold=self._settings.abandoned_object_proximity_threshold,
                    ):
                        self._abandoned_fired.add(key)
                        drafts.append(
                            EventDraft(
                                camera_id=event.camera_id,
                                event_type="Abandoned Object Detected",
                                object_type="bag",
                                severity="high",
                                description=(
                                    f"Unattended object present for over "
                                    f"{self._settings.abandoned_object_seconds_threshold}s with no person nearby"
                                ),
                                requires_review=True,
                            )
                        )

        elif event.event == "track.lost":
            counts.get(event.object_type, set()).discard(event.track_id)
            resolved_ref = self._alias.pop((event.camera_id, event.track_id), event.track_id)

            track = await track_repo.get_active(event.camera_id, resolved_ref)
            if track is not None:
                await track_repo.mark_lost(track, now)
            self._loitering_fired.discard((event.camera_id, resolved_ref))
            self._zone_state.pop((event.camera_id, resolved_ref), None)
            self._last_centroid.pop((event.camera_id, resolved_ref), None)
            self._last_centroid_time.pop((event.camera_id, resolved_ref), None)
            self._heading_history.pop((event.camera_id, resolved_ref), None)
            self._direction_last_emitted.pop((event.camera_id, resolved_ref), None)
            self._person_last_bbox.pop((event.camera_id, resolved_ref), None)
            self._displacement_history.pop((event.camera_id, resolved_ref), None)
            self._abandoned_fired.discard((event.camera_id, resolved_ref))
            self._fighting_fired = {
                pair_key for pair_key in self._fighting_fired
                if not (pair_key[0] == event.camera_id and resolved_ref in pair_key[1])
            }

            previous_density_zone_ids = self._track_density_zones.pop((event.camera_id, resolved_ref), None)
            if previous_density_zone_ids:
                for zone_id in previous_density_zone_ids:
                    self._zone_occupancy.get((event.camera_id, zone_id), set()).discard(resolved_ref)

            if track is not None and track.current_queue_zone_id is not None:
                await track_repo.set_current_queue_zone(track, None)

            previous_general_zone_id = self._general_zone_state.pop((event.camera_id, resolved_ref), None)
            if previous_general_zone_id is not None:
                # The track disappeared while still inside a general zone
                # (walked out of frame, occlusion that never reactivates,
                # etc.) -- that's a real exit, just not one a bbox update
                # ever reported; fetching the zone list here (rather than on
                # every track update) keeps this rare-path lookup off the
                # hot path.
                zones = await self._zone_provider(event.camera_id)
                zone_name = next((z.name for z in zones if z.id == previous_general_zone_id), "zone")
                drafts.append(
                    EventDraft(
                        camera_id=event.camera_id,
                        event_type="Zone Exit",
                        object_type=event.object_type,
                        severity="low",
                        description=f"Left zone '{zone_name}' (track lost)",
                        requires_review=True,
                    )
                )

            last_bbox = self._last_bbox.pop((event.camera_id, resolved_ref), None)
            if self._settings.enable_track_merge and last_bbox is not None:
                self._recently_lost.setdefault(event.camera_id, []).append(
                    _LostTrack(track_ref=resolved_ref, object_type=event.object_type, bbox=last_bbox, lost_at=now)
                )

        drafts.extend(self._check_count_threshold(event.camera_id, "person", self._settings.person_count_threshold))
        drafts.extend(self._check_count_threshold(event.camera_id, "vehicle", self._settings.vehicle_count_threshold))

        if event.bbox is not None and event.event in ("track.started", "track.updated"):
            zone_draft = await self._check_zone_entry(event, resolved_ref)
            if zone_draft is not None:
                drafts.append(zone_draft)
            drafts.extend(await self._check_general_zone_entry_exit(event, resolved_ref))
            drafts.extend(await self._check_crowd_density(event, resolved_ref))
            await self._check_queue_zone(event, resolved_ref, track_repo)

            # Line Crossing/Wrong-Way (M13/M14) and Speed Estimation (M14)
            # all need this update's centroid against the *previous* one --
            # computed once here rather than in each check separately, so
            # both see the same prev/curr pair and only one place advances
            # the stored "previous centroid" state.
            key = (event.camera_id, resolved_ref)
            cx, cy = zone_crossing.bbox_center(event.bbox)
            curr = Point(x=cx, y=cy)
            prev = self._last_centroid.get(key)
            prev_time = self._last_centroid_time.get(key)
            self._last_centroid[key] = curr
            self._last_centroid_time[key] = now

            drafts.extend(self._check_direction_analysis(event, resolved_ref, curr, now))

            if prev is not None:
                drafts.extend(await self._check_line_crossing(event, prev, curr))
                if prev_time is not None:
                    drafts.extend(await self._check_speed_estimation(event, prev, curr, prev_time, now))

            if event.object_type == "person":
                if prev is not None:
                    displacement = ((curr.x - prev.x) ** 2 + (curr.y - prev.y) ** 2) ** 0.5
                    history = self._displacement_history.setdefault(key, [])
                    history.append(displacement)
                    del history[: -self._settings.fighting_history_size]
                drafts.extend(self._check_fighting(event, resolved_ref, curr))
                self._person_last_bbox[key] = event.bbox

        return drafts

    async def handle_camera_status_changed(self, camera_id: str, status: str) -> list[EventDraft]:
        if not self._settings.offline_alert_enabled or not offline_alert.is_connection_lost(status):
            return []
        return [
            EventDraft(
                camera_id=camera_id,
                event_type="Connection Lost",
                object_type=None,
                severity="high",
                description="Camera stopped reporting a heartbeat",
                requires_review=True,
            )
        ]

    def _pop_merge_candidate(
        self, camera_id: str, object_type: str, bbox: BoundingBox, now: dt.datetime
    ) -> _LostTrack | None:
        """Finds the closest just-lost track of the same type, within the
        configured time+distance window, that this new sighting should be
        treated as a continuation of rather than a brand new one -- and
        removes it from the pool either way (matched, or simply expired)."""
        candidates = self._recently_lost.get(camera_id)
        if not candidates:
            return None

        window = self._settings.track_merge_window_seconds
        max_distance = self._settings.track_merge_max_distance_percent
        fresh = [c for c in candidates if (now - c.lost_at).total_seconds() <= window]

        best: _LostTrack | None = None
        best_distance = max_distance
        for candidate in fresh:
            if candidate.object_type != object_type:
                continue
            distance = _bbox_center_distance(candidate.bbox, bbox)
            if distance <= best_distance:
                best = candidate
                best_distance = distance

        self._recently_lost[camera_id] = [c for c in fresh if c is not best]
        return best

    def _check_count_threshold(self, camera_id: str, object_type: str, threshold: int) -> list[EventDraft]:
        count = len(self._active_counts.get(camera_id, {}).get(object_type, set()))
        key = (camera_id, object_type)
        over = count > threshold
        was_over = self._count_alert_active.get(key, False)
        self._count_alert_active[key] = over
        if not (over and not was_over):
            return []
        label = "Person Count Threshold Exceeded" if object_type == "person" else "Vehicle Count Threshold Exceeded"
        return [
            EventDraft(
                camera_id=camera_id,
                event_type=label,
                object_type=object_type,
                severity="low",
                description=f"{count} {object_type}s currently in frame (threshold {threshold})",
                requires_review=False,  # informational -- events log only, no alert (Frontend Analysis §3.5)
            )
        ]

    async def _check_zone_entry(self, event: TrackEvent, track_ref: str) -> EventDraft | None:
        zones = await self._zone_provider(event.camera_id)
        key = (event.camera_id, track_ref)
        if not zones:
            self._zone_state.pop(key, None)
            return None

        matched = intrusion.find_matching_zone(event.bbox, zones)  # type: ignore[arg-type]
        previous_zone_id = self._zone_state.get(key)
        new_zone_id = matched.id if matched else None
        self._zone_state[key] = new_zone_id

        if matched is None or new_zone_id == previous_zone_id:
            return None
        return EventDraft(
            camera_id=event.camera_id,
            event_type=intrusion.event_label_for_zone(matched),
            object_type=event.object_type,
            severity=intrusion.severity_for_zone(matched),
            description=f"Entered zone '{matched.name}'",
            requires_review=True,
        )

    async def _check_general_zone_entry_exit(self, event: TrackEvent, track_ref: str) -> list[EventDraft]:
        """Zone Entry/Exit (M13) -- `general`-type zones only (see
        `zone_crossing.find_general_zone`'s docstring for why restricted/
        perimeter stay `intrusion.py`'s exclusive territory). Handles all
        three transitions in one pass: entering a zone from outside any,
        leaving a zone to outside any, and moving directly from one general
        zone into another (fires both an exit and an entry)."""
        zones = await self._zone_provider(event.camera_id)
        key = (event.camera_id, track_ref)
        if not zones:
            self._general_zone_state.pop(key, None)
            return []

        matched = zone_crossing.find_general_zone(event.bbox, zones)  # type: ignore[arg-type]
        previous_zone_id = self._general_zone_state.get(key)
        new_zone_id = matched.id if matched else None
        self._general_zone_state[key] = new_zone_id

        if new_zone_id == previous_zone_id:
            return []

        drafts: list[EventDraft] = []
        if previous_zone_id is not None:
            previous_zone = next((z for z in zones if z.id == previous_zone_id), None)
            drafts.append(
                EventDraft(
                    camera_id=event.camera_id,
                    event_type="Zone Exit",
                    object_type=event.object_type,
                    severity="low",
                    description=f"Left zone '{previous_zone.name if previous_zone else 'zone'}'",
                    requires_review=True,
                )
            )
        if matched is not None:
            drafts.append(
                EventDraft(
                    camera_id=event.camera_id,
                    event_type="Zone Entry",
                    object_type=event.object_type,
                    severity="low",
                    description=f"Entered zone '{matched.name}'",
                    requires_review=True,
                )
            )
        return drafts

    async def _check_line_crossing(self, event: TrackEvent, prev: Point, curr: Point) -> list[EventDraft]:
        """Line Crossing (M13) + Wrong-Way Detection (M14): tests the
        track's movement segment (previous centroid -> current centroid)
        against every configured line each update, per doc09 §1.2. A line
        with no configured `direction` only ever produces "Line Crossing";
        one with a configured `direction` produces "Wrong-Way Movement"
        instead whenever the actual crossing direction doesn't match it.

        Fence Climbing Detection (behavioral analytics): a line whose
        `line_type == "fence"` marks it as a perimeter barrier rather than
        an ordinary road/lane boundary -- a *person* crossing one reports
        "Fence Climbing Detected" instead, ahead of the direction check
        above (a fence's `direction`, if set, still selects Wrong-Way vs.
        plain crossing semantics for non-person object types, but a person
        climbing a fence is never a "wrong way," it's the event). Every
        line with `line_type` unset (every line that existed before this
        feature) takes the exact same path as before -- nothing here
        changes for them.
        """
        lines = await self._zone_line_provider(event.camera_id)
        drafts: list[EventDraft] = []
        for line in lines:
            if not line_crossing.segments_intersect(prev, curr, line.point_a, line.point_b):
                continue
            crossing_dir = line_crossing.crossing_direction(line.point_a, line.point_b, prev, curr)
            if line.line_type == "fence" and event.object_type == "person":
                drafts.append(
                    EventDraft(
                        camera_id=event.camera_id,
                        event_type="Fence Climbing Detected",
                        object_type=event.object_type,
                        severity="critical",
                        description=f"Person crossed fence line '{line.name}' ({crossing_dir})",
                        requires_review=True,
                    )
                )
            elif line.direction is not None and crossing_dir != line.direction:
                drafts.append(
                    EventDraft(
                        camera_id=event.camera_id,
                        event_type="Wrong-Way Movement",
                        object_type=event.object_type,
                        severity="high",
                        description=f"Crossed line '{line.name}' against its configured direction ({crossing_dir})",
                        requires_review=True,
                    )
                )
            else:
                drafts.append(
                    EventDraft(
                        camera_id=event.camera_id,
                        event_type="Line Crossing",
                        object_type=event.object_type,
                        severity="medium",
                        description=f"Crossed line '{line.name}' ({crossing_dir})",
                        requires_review=True,
                    )
                )
        return drafts

    def _check_fighting(self, event: TrackEvent, track_ref: str, curr: Point) -> list[EventDraft]:
        """Fighting Detection (behavioral analytics): checks this
        just-updated person track against every other currently-tracked
        person on the same camera -- see `rules/fighting.py`'s own
        docstring for the proximity+erratic-motion heuristic and its
        honestly-disclosed limitations. Fires at most once per (camera,
        pair) per ongoing tracking episode -- like Loitering, a fresh
        episode starts once either track is lost and reappears."""
        camera_id = event.camera_id
        history_a = self._displacement_history.get((camera_id, track_ref), [])
        drafts: list[EventDraft] = []
        for (cam_id, other_ref), other_bbox in list(self._person_last_bbox.items()):
            if cam_id != camera_id or other_ref == track_ref:
                continue
            other_center = Point(x=other_bbox.x + other_bbox.width / 2, y=other_bbox.y + other_bbox.height / 2)
            distance = ((curr.x - other_center.x) ** 2 + (curr.y - other_center.y) ** 2) ** 0.5
            history_b = self._displacement_history.get((cam_id, other_ref), [])
            if not fighting.pair_is_fighting(
                distance, history_a, history_b,
                proximity_threshold=self._settings.fighting_proximity_threshold,
                jitter_threshold=self._settings.fighting_jitter_threshold,
                min_mean_displacement=self._settings.fighting_min_mean_displacement,
            ):
                continue
            pair_key = (camera_id, frozenset({track_ref, other_ref}))
            if pair_key in self._fighting_fired:
                continue
            self._fighting_fired.add(pair_key)
            drafts.append(
                EventDraft(
                    camera_id=camera_id,
                    event_type="Fighting Detected",
                    object_type="person",
                    severity="critical",
                    description="Two people in close, erratic contact -- possible physical altercation "
                                "(requires visual confirmation)",
                    requires_review=True,
                )
            )
        return drafts

    async def _check_speed_estimation(
        self, event: TrackEvent, prev: Point, curr: Point, prev_time: dt.datetime, now: dt.datetime
    ) -> list[EventDraft]:
        """Speed Estimation (M14): needs the camera's calibration (a one-time
        admin-configured pixel-to-meter mapping) -- silently does nothing
        for a camera that's never been calibrated, per doc09 §1.2 (no
        default/assumed calibration would be meaningful)."""
        if self._camera_info_provider is None:
            return []
        camera_info = await self._camera_info_provider(event.camera_id)
        if camera_info.calibration is None:
            return []

        pixels_moved = speed.pixel_distance(prev, curr)
        elapsed = (now - prev_time).total_seconds()
        kmh = speed.estimate_kmh(
            pixels_moved=pixels_moved,
            calibration_pixel_distance=camera_info.calibration.pixel_distance,
            calibration_real_world_meters=camera_info.calibration.real_world_meters,
            elapsed_seconds=elapsed,
        )
        if kmh <= camera_info.calibration.threshold_kmh:
            return []
        return [
            EventDraft(
                camera_id=event.camera_id,
                event_type="Speed Violation",
                object_type=event.object_type,
                severity="high",
                description=f"Estimated {kmh:.1f} km/h (threshold {camera_info.calibration.threshold_kmh} km/h)",
                requires_review=True,
            )
        ]

    def _check_direction_analysis(
        self, event: TrackEvent, track_ref: str, curr: Point, now: dt.datetime
    ) -> list[EventDraft]:
        """Direction Analysis (M14): informational only (`requires_review=
        False`, no alert) -- feeds the Analytics Service's `mv_direction_flow`
        materialized view, not the Alerts UI. Throttled to at most once/sec
        per track so a fast-updating track doesn't flood the events table."""
        key = (event.camera_id, track_ref)
        history = self._heading_history.setdefault(key, [])
        history.append(curr)
        del history[: -self._settings.direction_history_size]

        heading = direction.average_heading(history)
        if heading is None:
            return []

        last_emitted = self._direction_last_emitted.get(key)
        if (
            last_emitted is not None
            and (now - last_emitted).total_seconds() < self._settings.direction_emit_interval_seconds
        ):
            return []
        self._direction_last_emitted[key] = now

        bucket = direction.compass_bucket(*heading)
        return [
            EventDraft(
                camera_id=event.camera_id,
                event_type="Direction Observed",
                object_type=event.object_type,
                severity="low",
                description=f"Movement direction: {direction.describe(bucket)}",
                requires_review=False,
                direction=bucket,
            )
        ]

    async def _check_crowd_density(self, event: TrackEvent, track_ref: str) -> list[EventDraft]:
        """Crowd Density (M14): recomputed from the maintained per-zone
        occupancy set (not a one-shot per-track check), since density is a
        property of the *zone* at this instant, not any single track's
        transition. Any zone can opt in via `density_threshold` regardless
        of its `zone_type`."""
        if event.object_type != "person" or event.bbox is None:
            return []

        zones = await self._zone_provider(event.camera_id)
        density_zones = {z.id: z for z in zones if z.density_threshold is not None}
        if not density_zones:
            self._track_density_zones.pop((event.camera_id, track_ref), None)
            return []

        current_ids = {z.id for z in zone_crossing.zones_with_density_threshold(event.bbox, zones)}
        track_key = (event.camera_id, track_ref)
        previous_ids = self._track_density_zones.get(track_key, set())

        for zone_id in current_ids - previous_ids:
            self._zone_occupancy.setdefault((event.camera_id, zone_id), set()).add(track_ref)
        for zone_id in previous_ids - current_ids:
            self._zone_occupancy.get((event.camera_id, zone_id), set()).discard(track_ref)
        self._track_density_zones[track_key] = current_ids

        drafts: list[EventDraft] = []
        for zone_id in current_ids | previous_ids:
            zone = density_zones.get(zone_id)
            if zone is None or zone.density_threshold is None:
                continue
            area = zone_crossing.polygon_area(zone.polygon)
            if area < self._settings.minimum_zone_area_for_density:
                continue
            occupancy = self._zone_occupancy.get((event.camera_id, zone_id), set())
            zone_density = len(occupancy) / area
            alert_key = (event.camera_id, zone_id)
            over = zone_density > zone.density_threshold
            was_over = self._density_alert_active.get(alert_key, False)
            self._density_alert_active[alert_key] = over
            if over and not was_over:
                drafts.append(
                    EventDraft(
                        camera_id=event.camera_id,
                        event_type="Crowd Density",
                        object_type="person",
                        severity="medium",
                        description=(
                            f"Density {zone_density:.3f} exceeds threshold {zone.density_threshold} "
                            f"in zone '{zone.name}'"
                        ),
                        requires_review=True,
                    )
                )
        return drafts

    async def _check_queue_zone(self, event: TrackEvent, track_ref: str, track_repo: TrackRepository) -> None:
        """Queue Detection (M14): persists which `queue`-type zone (if any)
        this track currently occupies onto its DB row so the Analytics
        Service can compute live queue length/dwell time with a plain SQL
        query -- see `models/track.py`'s `current_queue_zone_id` docstring.
        Fires no event/alert itself; this is pure data for that query."""
        if event.bbox is None:
            return
        track = await track_repo.get_active(event.camera_id, track_ref)
        if track is None:
            return

        zones = await self._zone_provider(event.camera_id)
        matched = zone_crossing.find_queue_zone(event.bbox, zones)
        new_zone_id = matched.id if matched else None
        if track.current_queue_zone_id != new_zone_id:
            await track_repo.set_current_queue_zone(track, new_zone_id)
