from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "ppe-service"
    # No db_schema override -- this service has no database (doc09 §2.8's
    # only DB addition is `camera.zones.requires_ppe`, owned by
    # camera-service; a violation becomes a normal events/alerts row via
    # the shared internal event contract, same as fire-smoke/tamper).

    camera_service_url: str = "http://camera-service:8000"
    ingestion_service_url: str = "http://ingestion-service:8000"
    event_alert_service_url: str = "http://event-alert-service:8000"
    camera_refresh_interval_seconds: int = 15
    # How long a fetched zone list is trusted before re-fetching -- zones
    # are edited rarely (the M12 Zone Editor), same reasoning as
    # event-alert-service's own CameraClient cache.
    zones_refresh_interval_seconds: int = 60

    # Redis Streams consumer group on `cam:{id}:tracks` -- independent of
    # event-alert-service's and reid-service's own groups on the same
    # stream (SAS §11: multiple consumer groups per stream is the
    # documented pattern for this).
    consumer_group_name: str = "ppe-service"
    tracks_read_count: int = 10
    tracks_block_ms: int = 2000

    # Smallest person crop worth classifying -- a tiny/far-away crop has no
    # reliably resolvable helmet/vest region (doc11 §5: "crowded scenes and
    # partial visibility... reduce recall meaningfully").
    person_crop_min_size_px: int = 48

    # doc09 §2.5-style debounce, reused here: a person crossing briefly
    # through a requires_ppe zone with one bad frame shouldn't fire --
    # require this many consecutive track updates classified as missing
    # PPE before the first (medium-severity) violation event.
    violation_debounce_updates: int = 3
    # doc09 §2.8: "severity configurable... escalate to high for repeated
    # violations by the same track within a session" -- a second violation
    # event (severity high) fires once the same track has stayed in
    # violation for this many total consecutive updates past the initial
    # medium alert.
    escalation_violation_updates: int = 15

    # --- Color-region heuristic threshold (app/inference/ppe_heuristics.py) ---
    # Fraction of the crop's torso band that must match a high-visibility
    # color before a vest counts as present. doc11 §5's fallback is
    # explicitly scoped to "high-vis vests only" (no classical equivalent
    # for helmet presence is documented), so that's this service's only
    # checked PPE class -- see ppe_heuristics.py's own docstring.
    vest_min_coverage_fraction: float = 0.12


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
