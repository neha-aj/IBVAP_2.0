from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "tamper-service"
    # No db_schema override -- this service has no database (doc09 §2.5:
    # "DB additions: none"). CommonSettings.postgres_* fields still exist
    # only because docker-compose's shared env block sets them for every
    # service uniformly; nothing here ever opens a DB connection with them.

    camera_service_url: str = "http://camera-service:8000"
    event_alert_service_url: str = "http://event-alert-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:frames` -- independent of
    # detection-service's own group on the same stream (SAS §11: multiple
    # consumer groups per stream is the supported pattern for this).
    consumer_group_name: str = "tamper-service"
    frames_read_count: int = 5
    frames_block_ms: int = 2000

    # doc09 §2.5: "1fps is sufficient" -- tamper/coverage develops over
    # seconds, and a rolling statistical baseline doesn't benefit from a
    # higher sample rate the way a moving-object detector would.
    sample_interval_seconds: float = 1.0

    # --- Rolling baseline (app/inference/tamper_detector.py) ---
    # EMA update rate for the per-camera histogram/edge-density baseline --
    # low, so the baseline drifts with genuine gradual change (dawn/dusk
    # lighting) without absorbing a real tamper event as "the new normal"
    # (baseline updates are frozen entirely while a deviation is flagged,
    # regardless of this rate -- see TamperService).
    baseline_ema_alpha: float = 0.05

    # --- Deviation classification thresholds ---
    # cv2.compareHist HISTCMP_CORREL: 1.0 = identical, lower = more
    # different. A full-frame color shift (covered/blacked) crashes this
    # much harder than an ordinary scene change, hence the two different
    # correlation floors below.
    covered_correlation_threshold: float = 0.5
    redirected_correlation_threshold: float = 0.75
    # Fraction of current edge density vs. baseline edge density -- a
    # defocused or covered lens destroys fine detail, collapsing this
    # ratio, even when color/brightness alone wouldn't look that different.
    defocus_edge_ratio_threshold: float = 0.3

    # Consecutive *flagged* samples required before firing (doc09 §2.5:
    # "require the deviation to persist across several consecutive
    # samples...to avoid false positives from momentary lighting
    # changes"). At 1fps, 5 means ~5 seconds of sustained deviation.
    debounce_frames: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
