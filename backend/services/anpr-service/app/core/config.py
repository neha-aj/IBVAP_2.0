from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "anpr-service"
    db_schema: str = "anpr"

    # Discovery + snapshot fetch (same pattern as event-alert-service's
    # camera_service_url/ingestion_service_url).
    camera_service_url: str = "http://camera-service:8000"
    ingestion_service_url: str = "http://ingestion-service:8000"
    media_service_url: str = "http://media-service:8000"
    event_alert_service_url: str = "http://event-alert-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:detections` (doc09 §2.1:
    # "consumes cam:{id}:detections filtered server-side to vehicle").
    consumer_group_name: str = "anpr-service"
    detections_read_count: int = 10
    detections_block_ms: int = 2000

    # --- Plate detection/OCR (doc09 §2.1, doc11 §1) ---
    # Haar cascade + Tesseract chosen over YOLOv8-plate/PaddleOCR
    # specifically because no fine-tuned plate-detector weights or training
    # data exist for this deployment -- doc11 §1 explicitly sanctions this
    # pairing as the appropriate "offline/embedded... no GPU" fallback, not
    # a shortcut invented here. See Dockerfile's own comment.
    haar_cascade_name: str = "haarcascade_russian_plate_number.xml"
    min_plate_crop_height_px: int = 64  # doc09 §2.1: upscale if crop height < 64px
    min_ocr_confidence: float = 40.0  # Tesseract's own 0-100 per-word confidence scale
    # Validates OCR output looks plate-shaped at all (letters+digits, sane
    # length) rather than storing OCR garbage as a "read" -- doc09 §2.1's
    # own "regex/format validation against configurable regional plate
    # formats" recommendation, kept as one permissive default pattern
    # (deployment-specific formats are a config value, not a code change).
    plate_format_regex: str = r"^[A-Z0-9]{5,10}$"

    # Per-(camera, plate text) cooldown: `cam:{id}:detections` carries no
    # working track_id (detection-service always publishes `track_id=None`
    # on this stream -- tracking only happens downstream, on a separate
    # stream this service doesn't consume), so a car sitting in frame for
    # several seconds would otherwise be re-read and re-persisted on every
    # single detection message, flooding the License Plates page with
    # duplicate consecutive rows for the one easy-to-read vehicle. This
    # doesn't skip *detection* -- every vehicle is still localized/OCR'd
    # every time -- it only suppresses re-persisting the same plate text
    # again within the window, same reasoning as fire-smoke-service's own
    # per-camera-per-event-type cooldown.
    plate_read_cooldown_seconds: float = 30.0

    watchlist_severity: str = "critical"
    default_severity: str = "low"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
