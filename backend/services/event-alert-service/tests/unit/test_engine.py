import datetime as dt

import pytest

from app.core.config import Settings
from app.rules.engine import RuleEngine
from app.schemas.internal import BoundingBox, Calibration, CameraInfo, Point, TrackEvent, Zone, ZoneLine


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "person_count_threshold": 2, "vehicle_count_threshold": 2, "loitering_seconds_threshold": 30,
        "offline_alert_enabled": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class FakeTrack:
    def __init__(
        self, camera_id: str, track_ref: str, object_type: str, now: dt.datetime, loop_generation: int = 0
    ) -> None:
        self.camera_id = camera_id
        self.track_ref = track_ref
        self.object_type = object_type
        self.first_seen = now
        self.last_seen = now
        self.status = "active"
        self.loop_generation = loop_generation
        self.current_queue_zone_id: str | None = None


class FakeTrackRepo:
    def __init__(self) -> None:
        self.tracks: dict[tuple[str, str], FakeTrack] = {}

    async def get_active(self, camera_id: str, track_ref: str) -> FakeTrack | None:
        track = self.tracks.get((camera_id, track_ref))
        return track if track and track.status == "active" else None

    async def get_by_ref(self, camera_id: str, track_ref: str) -> FakeTrack | None:
        return self.tracks.get((camera_id, track_ref))

    async def start(
        self, *, camera_id: str, track_ref: str, object_type: str, now: dt.datetime, loop_generation: int = 0
    ) -> FakeTrack:
        track = FakeTrack(camera_id, track_ref, object_type, now, loop_generation)
        self.tracks[(camera_id, track_ref)] = track
        return track

    async def touch(self, track: FakeTrack, now: dt.datetime) -> None:
        track.last_seen = now

    async def mark_lost(self, track: FakeTrack, now: dt.datetime) -> None:
        track.status = "lost"
        track.last_seen = now

    async def reactivate(self, track: FakeTrack, now: dt.datetime) -> None:
        track.status = "active"
        track.last_seen = now

    async def set_current_queue_zone(self, track: FakeTrack, zone_id: str | None) -> None:
        track.current_queue_zone_id = zone_id


async def _no_zones(camera_id: str) -> list[Zone]:
    return []


def _track_event(
    event: str, track_id: str, object_type: str = "person", x: float = 10.0, y: float = 10.0,
    loop_generation: int = 0,
) -> TrackEvent:
    bbox = None if event == "track.lost" else BoundingBox(x=x, y=y, width=10.0, height=10.0)
    return TrackEvent(
        event=event, trackId=track_id, cameraId="CAM-01", objectType=object_type, bbox=bbox,
        loopGeneration=loop_generation,
    )


@pytest.mark.asyncio
async def test_count_threshold_fires_once_on_crossing() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    d1 = await engine.handle_track_event(_track_event("track.started", "1"), repo, now)
    d2 = await engine.handle_track_event(_track_event("track.started", "2"), repo, now)
    d3 = await engine.handle_track_event(_track_event("track.started", "3"), repo, now)

    assert not any(d.event_type == "Person Count Threshold Exceeded" for d in d1)
    assert not any(d.event_type == "Person Count Threshold Exceeded" for d in d2)
    assert any(d.event_type == "Person Count Threshold Exceeded" for d in d3)

    # A fourth track must not re-fire -- already over threshold.
    d4 = await engine.handle_track_event(_track_event("track.started", "4"), repo, now)
    assert not any(d.event_type == "Person Count Threshold Exceeded" for d in d4)


@pytest.mark.asyncio
async def test_count_drops_and_can_refire_on_next_crossing() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)
    for i in ["1", "2", "3"]:
        await engine.handle_track_event(_track_event("track.started", i), repo, now)

    # Drop below threshold, then cross again -- should fire a second time.
    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)
    await engine.handle_track_event(_track_event("track.lost", "2"), repo, now)
    drafts = await engine.handle_track_event(_track_event("track.started", "5"), repo, now)
    drafts += await engine.handle_track_event(_track_event("track.started", "6"), repo, now)

    assert any(d.event_type == "Person Count Threshold Exceeded" for d in drafts)


@pytest.mark.asyncio
async def test_loitering_fires_once_after_threshold() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    start_time = dt.datetime.now(dt.UTC)
    await engine.handle_track_event(_track_event("track.started", "1"), repo, start_time)

    still_early = start_time + dt.timedelta(seconds=5)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1"), repo, still_early)
    assert not any(d.event_type == "Loitering Detected" for d in drafts)

    past_threshold = start_time + dt.timedelta(seconds=31)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1"), repo, past_threshold)
    assert any(d.event_type == "Loitering Detected" for d in drafts)

    # Must not re-fire on the next update for the same still-loitering track.
    later = start_time + dt.timedelta(seconds=40)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1"), repo, later)
    assert not any(d.event_type == "Loitering Detected" for d in drafts)


@pytest.mark.asyncio
async def test_zone_entry_fires_once_then_not_again_until_re_entry() -> None:
    zone = Zone(
        id="zone-1", name="Perimeter", zone_type="perimeter",
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    # Enters the zone (x=10 -> center inside the 0-100 square).
    drafts = await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    assert any(d.event_type == "Fence Intrusion" for d in drafts)

    # Still inside on the next update -- must not re-fire.
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=15.0), repo, now)
    assert not any(d.event_type == "Fence Intrusion" for d in drafts)


@pytest.mark.asyncio
async def test_loop_generation_threads_through_to_track_repo() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", loop_generation=0), repo, now)
    await engine.handle_track_event(_track_event("track.started", "2", loop_generation=3), repo, now)

    assert repo.tracks[("CAM-01", "1")].loop_generation == 0
    assert repo.tracks[("CAM-01", "2")].loop_generation == 3


@pytest.mark.asyncio
async def test_redelivered_track_started_touches_instead_of_restarting() -> None:
    """A `track.started` for a ref that's already active (at-least-once
    stream redelivery, e.g. reprocessing unacked entries after a restart)
    must not fork a second row for the same physical track -- `first_seen`
    staying put (rather than resetting) is the observable proof it was
    touched, not restarted."""
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    start_time = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1"), repo, start_time)
    redelivered_at = start_time + dt.timedelta(seconds=5)
    await engine.handle_track_event(_track_event("track.started", "1"), repo, redelivered_at)

    track = repo.tracks[("CAM-01", "1")]
    assert track.first_seen == start_time
    assert track.last_seen == redelivered_at


@pytest.mark.asyncio
async def test_merge_reactivates_nearby_track_instead_of_starting_new() -> None:
    engine = RuleEngine(_settings(track_merge_window_seconds=2.0, track_merge_max_distance_percent=15.0), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)

    # A new raw track id, but appearing right where "1" vanished, moments later.
    reappeared = now + dt.timedelta(seconds=1)
    await engine.handle_track_event(_track_event("track.started", "2", x=11.0), repo, reappeared)

    # No new row for "2" -- "1"'s original row was reactivated instead.
    assert ("CAM-01", "2") not in repo.tracks
    assert repo.tracks[("CAM-01", "1")].status == "active"
    assert repo.tracks[("CAM-01", "1")].first_seen == now  # dwell time preserved, not reset


@pytest.mark.asyncio
async def test_merge_ignores_a_track_that_reappears_far_away() -> None:
    engine = RuleEngine(_settings(track_merge_window_seconds=2.0, track_merge_max_distance_percent=15.0), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)

    far_away = now + dt.timedelta(seconds=1)
    await engine.handle_track_event(_track_event("track.started", "2", x=90.0), repo, far_away)

    # Far from where "1" vanished -- counted as a genuinely new track.
    assert ("CAM-01", "2") in repo.tracks
    assert repo.tracks[("CAM-01", "1")].status == "lost"


@pytest.mark.asyncio
async def test_merge_ignores_a_track_that_reappears_after_the_window() -> None:
    engine = RuleEngine(_settings(track_merge_window_seconds=2.0, track_merge_max_distance_percent=15.0), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)

    too_late = now + dt.timedelta(seconds=5)
    await engine.handle_track_event(_track_event("track.started", "2", x=11.0), repo, too_late)

    # Nearby, but well outside the merge window -- counted as new.
    assert ("CAM-01", "2") in repo.tracks


@pytest.mark.asyncio
async def test_merge_disabled_by_toggle_starts_a_new_track() -> None:
    engine = RuleEngine(_settings(enable_track_merge=False), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)

    reappeared = now + dt.timedelta(seconds=1)
    await engine.handle_track_event(_track_event("track.started", "2", x=11.0), repo, reappeared)

    # Toggle off -- behaves exactly like before the merge heuristic existed.
    assert ("CAM-01", "2") in repo.tracks
    assert repo.tracks[("CAM-01", "1")].status == "lost"


@pytest.mark.asyncio
async def test_merged_track_continues_to_update_and_can_be_lost_again() -> None:
    engine = RuleEngine(_settings(track_merge_window_seconds=2.0, track_merge_max_distance_percent=15.0), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)
    reappeared = now + dt.timedelta(seconds=1)
    await engine.handle_track_event(_track_event("track.started", "2", x=11.0), repo, reappeared)

    # Further lifecycle events for the new raw id ("2") must resolve to the
    # same merged row, not silently no-op or create yet another new row.
    updated_at = reappeared + dt.timedelta(seconds=1)
    await engine.handle_track_event(_track_event("track.updated", "2", x=12.0), repo, updated_at)
    assert repo.tracks[("CAM-01", "1")].last_seen == updated_at

    lost_at = updated_at + dt.timedelta(seconds=1)
    await engine.handle_track_event(_track_event("track.lost", "2"), repo, lost_at)
    assert repo.tracks[("CAM-01", "1")].status == "lost"
    assert ("CAM-01", "2") not in repo.tracks


@pytest.mark.asyncio
async def test_camera_offline_fires_connection_lost() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    drafts = await engine.handle_camera_status_changed("CAM-01", "offline")
    assert len(drafts) == 1
    assert drafts[0].event_type == "Connection Lost"
    assert drafts[0].requires_review is True


@pytest.mark.asyncio
async def test_camera_online_fires_nothing() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    drafts = await engine.handle_camera_status_changed("CAM-01", "online")
    assert drafts == []


@pytest.mark.asyncio
async def test_offline_alert_disabled_fires_nothing() -> None:
    engine = RuleEngine(_settings(offline_alert_enabled=False), _no_zones)
    drafts = await engine.handle_camera_status_changed("CAM-01", "offline")
    assert drafts == []


# --- Zone Entry/Exit (M13) ---


@pytest.mark.asyncio
async def test_general_zone_entry_and_exit_fire_distinct_events() -> None:
    zone = Zone(
        id="zone-1", name="Lobby", zone_type="general",
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    # Enters the zone.
    drafts = await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    assert any(d.event_type == "Zone Entry" for d in drafts)
    assert not any(d.event_type == "Zone Exit" for d in drafts)

    # Still inside on the next update -- must not re-fire either event.
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=15.0), repo, now)
    assert not any(d.event_type in ("Zone Entry", "Zone Exit") for d in drafts)

    # Moves outside the polygon -- fires Exit, not another Entry.
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=200.0), repo, now)
    assert any(d.event_type == "Zone Exit" for d in drafts)
    assert not any(d.event_type == "Zone Entry" for d in drafts)


@pytest.mark.asyncio
async def test_general_zone_does_not_double_fire_with_restricted_intrusion() -> None:
    """A `general` zone must never produce `Fence Intrusion`/`Restricted
    Zone Entry` -- those stay exclusive to restricted/perimeter zones,
    otherwise every general-zone entry would double-alert."""
    zone = Zone(
        id="zone-1", name="Lobby", zone_type="general",
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    drafts = await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    assert not any(d.event_type in ("Fence Intrusion", "Restricted Zone Entry") for d in drafts)


@pytest.mark.asyncio
async def test_zone_exit_fires_when_track_is_lost_while_inside() -> None:
    zone = Zone(
        id="zone-1", name="Lobby", zone_type="general",
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0), repo, now)
    drafts = await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)
    assert any(d.event_type == "Zone Exit" for d in drafts)


# --- Line Crossing (M13) ---


def _zone_line_provider(lines: list[ZoneLine]):
    async def provider(camera_id: str) -> list[ZoneLine]:
        return lines

    return provider


@pytest.mark.asyncio
async def test_line_crossing_fires_when_track_crosses_configured_line() -> None:
    line = ZoneLine(id="line-1", name="Boundary", point_a=Point(x=0, y=50), point_b=Point(x=100, y=50))
    engine = RuleEngine(_settings(), _no_zones, _zone_line_provider([line]))
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    # First sighting: no previous centroid yet, so nothing can fire.
    drafts = await engine.handle_track_event(_track_event("track.started", "1", x=50.0, y=10.0), repo, now)
    assert not any(d.event_type == "Line Crossing" for d in drafts)

    # Moves from above the line (y=10) to below it (y=90) -- crosses.
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=50.0, y=90.0), repo, now)
    assert any(d.event_type == "Line Crossing" for d in drafts)


@pytest.mark.asyncio
async def test_line_crossing_does_not_fire_without_crossing() -> None:
    line = ZoneLine(id="line-1", name="Boundary", point_a=Point(x=0, y=50), point_b=Point(x=100, y=50))
    engine = RuleEngine(_settings(), _no_zones, _zone_line_provider([line]))
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=50.0, y=10.0), repo, now)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=60.0, y=15.0), repo, now)
    assert not any(d.event_type == "Line Crossing" for d in drafts)


@pytest.mark.asyncio
async def test_line_crossing_disabled_when_no_lines_configured() -> None:
    engine = RuleEngine(_settings(), _no_zones)  # zone_line_provider defaults to "no lines"
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=50.0, y=10.0), repo, now)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=50.0, y=90.0), repo, now)
    assert not any(d.event_type == "Line Crossing" for d in drafts)


# --- Wrong-Way Detection (M14) ---


@pytest.mark.asyncio
async def test_wrong_way_fires_instead_of_line_crossing_against_configured_direction() -> None:
    line = ZoneLine(
        id="line-1", name="Boundary", point_a=Point(x=0, y=50), point_b=Point(x=100, y=50), direction="a_to_b",
    )
    engine = RuleEngine(_settings(), _no_zones, _zone_line_provider([line]))
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=50.0, y=90.0), repo, now)
    # This crossing direction is "a_to_b" (see test_line_crossing.py's own
    # verified convention for these exact coordinates).
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=50.0, y=10.0), repo, now)
    assert any(d.event_type == "Line Crossing" for d in drafts)
    assert not any(d.event_type == "Wrong-Way Movement" for d in drafts)

    # Reverse the crossing -- now "b_to_a", against the configured direction.
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=50.0, y=90.0), repo, now)
    assert any(d.event_type == "Wrong-Way Movement" for d in drafts)
    assert not any(d.event_type == "Line Crossing" for d in drafts)


@pytest.mark.asyncio
async def test_line_without_configured_direction_never_fires_wrong_way() -> None:
    line = ZoneLine(id="line-1", name="Boundary", point_a=Point(x=0, y=50), point_b=Point(x=100, y=50))
    engine = RuleEngine(_settings(), _no_zones, _zone_line_provider([line]))
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=50.0, y=10.0), repo, now)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=50.0, y=90.0), repo, now)
    assert not any(d.event_type == "Wrong-Way Movement" for d in drafts)
    assert any(d.event_type == "Line Crossing" for d in drafts)


# --- Speed Estimation (M14) ---


def _camera_info_provider(calibration: Calibration | None):
    async def provider(camera_id: str) -> CameraInfo:
        return CameraInfo(id=camera_id, name="Cam", location="Loc", calibration=calibration)

    return provider


@pytest.mark.asyncio
async def test_speed_violation_fires_above_threshold() -> None:
    calibration = Calibration(pixel_distance=10.0, real_world_meters=5.0, threshold_kmh=10.0)
    engine = RuleEngine(_settings(), _no_zones, camera_info_provider=_camera_info_provider(calibration))
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=0.0, y=10.0), repo, now)
    # Moves 10 (frame-percentage) pixels in 1 second -> 5 m/s -> 18 km/h,
    # over the 10 km/h threshold (see test_speed.py's own verified math).
    later = now + dt.timedelta(seconds=1)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=10.0, y=10.0), repo, later)
    assert any(d.event_type == "Speed Violation" for d in drafts)


@pytest.mark.asyncio
async def test_no_speed_check_without_camera_calibration() -> None:
    engine = RuleEngine(_settings(), _no_zones, camera_info_provider=_camera_info_provider(None))
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=0.0, y=10.0), repo, now)
    later = now + dt.timedelta(seconds=1)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=10.0, y=10.0), repo, later)
    assert not any(d.event_type == "Speed Violation" for d in drafts)


# --- Direction Analysis (M14) ---


@pytest.mark.asyncio
async def test_direction_observed_fires_informational_event_with_bucket() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=0.0, y=10.0), repo, now)
    later = now + dt.timedelta(seconds=2)
    drafts = await engine.handle_track_event(_track_event("track.updated", "1", x=10.0, y=10.0), repo, later)

    direction_drafts = [d for d in drafts if d.event_type == "Direction Observed"]
    assert len(direction_drafts) == 1
    assert direction_drafts[0].requires_review is False
    assert direction_drafts[0].direction == "E"


@pytest.mark.asyncio
async def test_direction_observed_is_throttled_to_once_per_second() -> None:
    engine = RuleEngine(_settings(), _no_zones)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=0.0, y=10.0), repo, now)
    first = now + dt.timedelta(seconds=2)
    drafts1 = await engine.handle_track_event(_track_event("track.updated", "1", x=10.0, y=10.0), repo, first)
    assert any(d.event_type == "Direction Observed" for d in drafts1)

    # 200ms later -- well under the 1s throttle window.
    soon_after = first + dt.timedelta(milliseconds=200)
    drafts2 = await engine.handle_track_event(_track_event("track.updated", "1", x=11.0, y=10.0), repo, soon_after)
    assert not any(d.event_type == "Direction Observed" for d in drafts2)


# --- Crowd Density (M14) ---


@pytest.mark.asyncio
async def test_crowd_density_fires_once_when_occupancy_crosses_threshold() -> None:
    zone = Zone(
        id="zone-1", name="Dense Area", zone_type="general", density_threshold=0.01,
        polygon=[Point(x=0, y=0), Point(x=10, y=0), Point(x=10, y=10), Point(x=0, y=10)],  # area = 100
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    # One person: density 1/100 = 0.01, not strictly over threshold yet.
    drafts = await engine.handle_track_event(_track_event("track.started", "1", x=1.0, y=1.0), repo, now)
    assert not any(d.event_type == "Crowd Density" for d in drafts)

    # A second person pushes density to 2/100 = 0.02, over the threshold.
    drafts = await engine.handle_track_event(_track_event("track.started", "2", x=2.0, y=2.0), repo, now)
    assert any(d.event_type == "Crowd Density" for d in drafts)

    # A third person update while still over threshold must not re-fire.
    drafts = await engine.handle_track_event(_track_event("track.updated", "2", x=3.0, y=3.0), repo, now)
    assert not any(d.event_type == "Crowd Density" for d in drafts)


@pytest.mark.asyncio
async def test_crowd_density_ignores_vehicles() -> None:
    zone = Zone(
        id="zone-1", name="Dense Area", zone_type="general", density_threshold=0.0001,
        polygon=[Point(x=0, y=0), Point(x=10, y=0), Point(x=10, y=10), Point(x=0, y=10)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    drafts = await engine.handle_track_event(
        _track_event("track.started", "1", object_type="vehicle", x=1.0, y=1.0), repo, now
    )
    assert not any(d.event_type == "Crowd Density" for d in drafts)


# --- Queue Detection (M14) ---


@pytest.mark.asyncio
async def test_queue_zone_persists_onto_track_row() -> None:
    zone = Zone(
        id="queue-1", name="Checkout Line", zone_type="queue",
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0, y=10.0), repo, now)
    assert repo.tracks[("CAM-01", "1")].current_queue_zone_id == "queue-1"

    # Moves outside the queue zone -- cleared back to None.
    await engine.handle_track_event(_track_event("track.updated", "1", x=200.0, y=200.0), repo, now)
    assert repo.tracks[("CAM-01", "1")].current_queue_zone_id is None


@pytest.mark.asyncio
async def test_queue_zone_cleared_when_track_is_lost() -> None:
    zone = Zone(
        id="queue-1", name="Checkout Line", zone_type="queue",
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )

    async def zones_provider(camera_id: str) -> list[Zone]:
        return [zone]

    engine = RuleEngine(_settings(), zones_provider)
    repo = FakeTrackRepo()
    now = dt.datetime.now(dt.UTC)

    await engine.handle_track_event(_track_event("track.started", "1", x=10.0, y=10.0), repo, now)
    assert repo.tracks[("CAM-01", "1")].current_queue_zone_id == "queue-1"

    await engine.handle_track_event(_track_event("track.lost", "1"), repo, now)
    assert repo.tracks[("CAM-01", "1")].current_queue_zone_id is None
