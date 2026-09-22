from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "media-service"
    db_schema: str = "media"

    media_root: str = "/data/media"
    # Public URL prefix nginx serves `media_root` under (see
    # nginx/conf.d/api-gateway.conf `location /media/`) -- stored/returned
    # snapshot URLs are relative paths under this prefix, resolved directly
    # by nginx as static files rather than round-tripping through this
    # service on every read (matches how Stream Ingestion's MJPEG preview
    # is served -- a plain URL, no auth, no extra hop).
    media_url_prefix: str = "/media"
    max_upload_size_bytes: int = 20 * 1024 * 1024  # 20MB -- a single JPEG frame, generous
    # Phase 2 M23: camera-service's own upload proxy (a full source video,
    # not a single frame) and the recording-clip producer's short clips --
    # much larger than a snapshot, so each gets its own ceiling rather than
    # sharing `max_upload_size_bytes`.
    max_source_upload_size_bytes: int = 2 * 1024 * 1024 * 1024  # 2GB, matches nginx client_max_body_size
    max_recording_upload_size_bytes: int = 200 * 1024 * 1024  # 200MB -- a short post-roll clip

    # M25: independent hash-chained anchor service (see app/services/
    # ledger_service.py). A URL, not a hard requirement -- every call
    # through it degrades gracefully if unreachable.
    ledger_service_url: str = "http://ledger-service:8000"
    ledger_request_timeout_seconds: float = 3.0

    # M25 anomaly detection: reports an unusual burst of evidence downloads/
    # verifies through event-alert-service's existing internal event
    # contract (doc08 §4) -- see app/services/anomaly_service.py.
    event_alert_service_url: str = "http://event-alert-service:8000"
    anomaly_window_seconds: int = 60
    anomaly_burst_threshold: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
