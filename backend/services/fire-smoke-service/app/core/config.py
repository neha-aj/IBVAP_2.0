from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "fire-smoke-service"
    # No db_schema override -- this service has no database (doc09 §2.6:
    # "DB additions: none beyond media.snapshots", and that snapshot write
    # already happens inside event-alert-service's existing per-event
    # capture path, not here). CommonSettings.postgres_* fields still exist
    # only because docker-compose's shared env block sets them for every
    # service uniformly; nothing here ever opens a DB connection with them.

    camera_service_url: str = "http://camera-service:8000"
    event_alert_service_url: str = "http://event-alert-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:frames` -- independent of
    # detection-service's own group on the same stream (SAS §11: multiple
    # consumer groups per stream is the supported pattern for this).
    consumer_group_name: str = "fire-smoke-service"
    frames_read_count: int = 5
    frames_block_ms: int = 2000

    # doc09 §2.6: "2-5fps is standard for this use case -- fire/smoke
    # develops over seconds, not milliseconds". Implemented as a minimum
    # wall-clock gap between processed frames per camera (frames arriving
    # faster than this are ack'd but skipped, not queued) rather than
    # subscribing at a lower rate, since `cam:{id}:frames` is shared with
    # detection-service's own full-framerate consumer group.
    sample_interval_seconds: float = 0.3  # ~3fps

    # --- Fire/smoke heuristic thresholds (app/inference/heuristics.py) ---
    # Fraction of frame pixels that must match the fire-color/smoke-texture
    # profile before it counts as a detection -- tuned to avoid firing on
    # small compression artifacts or a single stray warm-colored object,
    # not validated against a real adversarial dataset (see heuristics.py's
    # own docstring for the honest accuracy caveat this implies).
    #
    # Raised from 0.02: live-tested against this deployment's own camera
    # feeds, which produced 36 real false-positive "Fire Detected" alerts
    # on a red car passing through frame, with reported coverage ranging
    # 2-7% across every one of them (never higher) -- 0.02 was catching
    # essentially all of them. 0.15 keeps a real safety margin above that
    # observed false-positive ceiling (same reasoning and same value as
    # smoke_min_area_fraction below, which was tuned against its own
    # observed false-positive residuals the same way).
    fire_min_area_fraction: float = 0.15
    # 0.15: live-tested against this deployment's own camera feeds, whose
    # real (harmless) smoke_score residuals after heuristics.py's texture+
    # sky-band fixes topped out around 0.035 -- 0.15 keeps a real safety
    # margin above that observed false-positive floor while staying
    # reachable by genuine large smoke coverage.
    smoke_min_area_fraction: float = 0.15

    # Per-camera-per-class cooldown: doc09 §2.6 says a detection "bypasses
    # any per-alert debounce...a single high-confidence frame should alert
    # immediately" -- which this honors (the *first* detection always
    # fires with zero delay). This cooldown only suppresses *repeat* alerts
    # while a fire/smoke condition is still continuously present at
    # 2-5fps, so a real sustained fire doesn't produce one alert per frame
    # forever.
    alert_cooldown_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
