from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "event-alert-service"
    db_schema: str = "events"

    # Camera Management Service (M2) -- same discovery pattern as every
    # downstream pipeline stage, plus resolving camera name/location for
    # denormalized event/alert rows and reading configured zones.
    camera_service_url: str = "http://camera-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:tracks` (SAS §5.4 step 1).
    consumer_group_name: str = "event-alert-service"
    tracks_read_count: int = 10
    tracks_block_ms: int = 2000

    # How often (in reconcile passes) to re-fetch a camera's configured
    # zones -- zones essentially never change at runtime today (no public
    # edit API yet), so this doesn't need to be aggressive.
    zones_refresh_interval_seconds: int = 60

    # --- Rule thresholds (Phase 1 rules, SAS §5.4.2) ---
    person_count_threshold: int = 5
    vehicle_count_threshold: int = 3
    loitering_seconds_threshold: int = 30
    offline_alert_enabled: bool = True

    # --- Alert threshold (Phase 2 hardening) ---
    # Every fired rule always becomes an `events` row (the full audit log).
    # A rule marked `requires_review=True` additionally becomes an `alerts`
    # row -- but some of those (Zone Entry/Exit today) are only ever
    # "low" severity and fire on completely routine movement, so on a busy
    # or looping camera they can flood the Alerts page with things nobody
    # actually needs to act on. This floor gates alert *creation* on
    # severity too: below it, a `requires_review` firing still shows up in
    # Events, it just doesn't also raise an Alert. Raise/lower per
    # deployment by changing this one value -- "low"/"medium"/"high"/
    # "critical".
    alert_min_severity: str = "medium"

    # --- Track merge heuristic ---
    # A tracker losing and immediately reacquiring the same real person
    # (occlusion, one low-confidence frame, a reflection glitch) otherwise
    # counts as a brand new person. When enabled, a `track.started` that
    # appears shortly after -- and near where -- a just-lost track of the
    # same type vanished is treated as that same track continuing, not a
    # new one. Toggle off to fully restore pre-merge counting behavior.
    enable_track_merge: bool = True
    track_merge_window_seconds: float = 2.0
    track_merge_max_distance_percent: float = 15.0

    # --- Phase 2 M14 Rule Extension Pack 2 ---
    # Direction Analysis: how many recent centroid positions the moving-
    # average heading is computed from. Smaller = more responsive to sudden
    # turns; larger = smoother but slower to reflect a real direction change.
    direction_history_size: int = 5
    # How often (per track) a "Direction Observed" row is allowed to be
    # emitted. This is analytics telemetry (feeds `mv_direction_flow`), not
    # something an operator needs to review one-by-one -- at the old 1
    # second value, a handful of simultaneously-moving tracks (e.g. several
    # looping demo cameras) floods the Events log with thousands of rows an
    # hour that are all "informational only" anyway. 5s keeps enough
    # resolution for a meaningful flow trend without the flood.
    direction_emit_interval_seconds: float = 5.0
    # Crowd Density: minimum polygon area (percent-of-frame-squared) before
    # a density figure is considered meaningful -- an operator-drawn zone
    # that's nearly a single point would otherwise divide by a near-zero
    # area and produce a wildly inflated, meaningless density value.
    minimum_zone_area_for_density: float = 1.0

    # --- Snapshot capture (SAS §5.4 step 4, §5.5) ---
    ingestion_service_url: str = "http://ingestion-service:8000"
    media_service_url: str = "http://media-service:8000"
    # A snapshot round-trip (two internal HTTP calls) shouldn't be allowed
    # to stall event creation if either service is slow/down -- capture is
    # best-effort (SAS §11 graceful degradation), never blocking the event
    # itself from being persisted.
    snapshot_capture_timeout_seconds: float = 5.0

    # --- Recording clip capture (Phase 2 M23) ---
    # Critical-severity events only (doc09/doc08's own "critical-severity
    # recording trigger" concept, never actually wired to a producer until
    # M23 -- see media-service's `Recording` model docstring).
    recording_post_roll_frame_count: int = 15
    recording_post_roll_interval_seconds: float = 0.2
    # Playback frame rate of the assembled clip -- frames were captured
    # `recording_post_roll_interval_seconds` apart, so 1/interval keeps
    # playback speed close to real time.
    recording_clip_fps: float = 5.0
    recording_capture_timeout_seconds: float = 10.0
    # Accident/event evidence: true pre-roll, now that ingestion-service
    # keeps a rolling FrameRingBuffer per camera (previously only a single
    # latest frame was cached, which is why this was post-roll-only -- see
    # git history/PROGRESS.md for that earlier, honestly-scoped limitation).
    # Must be <= ingestion-service's own `preroll_buffer_seconds`, a
    # separate setting on that service -- this is what's actually
    # *requested*, that's the ceiling on what the buffer *can* hold.
    recording_pre_roll_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
