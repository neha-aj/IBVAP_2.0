from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "ingestion-service"

    # Camera Management Service (M2) -- source of truth for which cameras
    # exist and how to open them.
    camera_service_url: str = "http://camera-service:8000"

    # How often to re-poll the camera list for adds/removals.
    camera_refresh_interval_seconds: int = 15

    # Frames actually decoded/read per camera per second from the source.
    capture_fps: int = 15
    # Subset of those frames pushed onto the Redis Stream for downstream AI
    # (SAS §5.1: "downsamples to a configurable inference FPS").
    inference_fps: int = 5

    # If no frame has been read in this many seconds, the camera is marked offline.
    heartbeat_timeout_seconds: int = 10
    # Below this fraction of `capture_fps`, the camera is marked "warning" instead of "online".
    warning_fps_ratio: float = 0.5

    # A separate, longer failsafe from `heartbeat_timeout_seconds`: that one
    # only fires when the blocking read *returns* None repeatedly. Observed
    # live: OpenCV/FFmpeg's `VideoCapture.read()` can instead hang forever on
    # a long-looping file source, never returning at all -- the worker task
    # then looks like it's still "running" indefinitely with no way to
    # detect its own hang from the inside. WorkerManager polls
    # `CameraWorker.seconds_since_last_frame()` against this and force-
    # replaces a worker that's exceeded it, even though `is_running` still
    # reports True. Well above `heartbeat_timeout_seconds` and the poll
    # interval so a worker isn't churned for an ordinary transient stall.
    stuck_worker_timeout_seconds: int = 60

    # How many entries to keep per Redis Stream before trimming (SAS §11 backpressure).
    frame_stream_maxlen: int = 200

    # JPEG quality for both the Redis-published frame and the MJPEG preview.
    jpeg_quality: int = 70

    # For `file`-type cameras: loop back to the start on end-of-stream so a
    # short test clip behaves like a continuous camera feed.
    loop_file_sources: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
