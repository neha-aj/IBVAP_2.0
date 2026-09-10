from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "tracking-service"

    # Camera Management Service (M2) -- same discovery pattern as Ingestion
    # (M3) and Detection (M4): poll for which cameras exist.
    camera_service_url: str = "http://camera-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:detections` (SAS §5.3).
    # Distinct group name from Detection Service's own group (which reads a
    # *different* stream, `cam:{id}:frames`) -- no collision, but named
    # separately for clarity in `XINFO GROUPS`.
    consumer_group_name: str = "tracking-service"
    detections_read_count: int = 5
    detections_block_ms: int = 2000

    # How many entries to keep per `cam:{id}:tracks` stream before trimming
    # (SAS §11 backpressure), mirroring detection-service's stream maxlen.
    tracks_stream_maxlen: int = 500

    # TTL on the `cam:{id}:current_detections` cache key this service
    # overwrites with track-enriched data -- must match (or exceed) Detection
    # Service's own TTL so the overlay doesn't flicker between writers.
    current_detections_ttl_seconds: int = 5

    # ByteTrack tuning (SAS §5.3 "feeds ByteTrack, assigns/persists track_id").
    # `frame_rate` should match ingestion's `inference_fps` (the rate frames
    # actually arrive at this pipeline stage), not the camera's raw fps --
    # it only affects ByteTrack's internal buffer-time bookkeeping.
    track_frame_rate: int = 5
    track_activation_threshold: float = 0.25
    # ~1s of real grace time at the default track_frame_rate (30 -> 60
    # roughly doubles it to ~2s) -- a brief occlusion or one-off missed
    # detection no longer drops the track and reassigns a new id on the
    # object's very next appearance.
    lost_track_buffer_frames: int = 60
    minimum_matching_threshold: float = 0.8
    # Requires a detection to match across this many consecutive frames
    # before ByteTrack promotes it to a real track_id -- without this,
    # single-frame flicker (a momentary false-positive detection) gets
    # counted as a brand new person/vehicle. supervision's default (1)
    # means no filtering at all.
    minimum_consecutive_frames: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
