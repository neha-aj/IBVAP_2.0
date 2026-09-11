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
    # Raised from 15 -- the live-preview tile was visibly capped below this
    # (see preview_fps below), and 15 was the tighter of the two limits.
    # Purely a capture/preview-smoothness knob: inference_fps (below) is
    # unchanged, so this has zero effect on detection/tracking load or
    # accuracy, only on how often the preview JPEG is refreshed.
    capture_fps: int = 30
    # Subset of those frames pushed onto the Redis Stream for downstream AI
    # (SAS §5.1: "downsamples to a configurable inference FPS").
    inference_fps: int = 5

    # How often `/stream/{id}/mjpeg` emits a frame to the browser. Was a
    # hardcoded `asyncio.sleep(0.1)` (~10fps) in preview.py regardless of
    # `capture_fps` -- the actual bottleneck behind the live-preview tile
    # looking laggier than the real camera. Matched to capture_fps so the
    # preview is only ever as fresh as the frames actually being captured.
    preview_fps: int = 30

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
    # Raised from 70 for a visibly sharper live-preview image; still well
    # short of 100 (diminishing returns there mean much larger frames for
    # barely-visible gain, which would add latency, not remove it).
    jpeg_quality: int = 85

    # For `file`-type cameras: loop back to the start on end-of-stream so a
    # short test clip behaves like a continuous camera feed.
    loop_file_sources: bool = True

    # --- Evidence pre-roll buffer (accident/event recording) ---
    # How much rolling history `FrameRingBuffer` keeps per camera. Must be
    # >= event-alert-service's `recording_pre_roll_seconds` (a separate
    # service/setting) or a pre-roll request would ask for more history
    # than exists; kept a few seconds above that service's 30s default as
    # headroom rather than coupling the two settings directly.
    preroll_buffer_seconds: int = 45
    # Sampled well below capture_fps -- pre-roll evidence doesn't need full
    # frame-rate fidelity, and buffering every captured frame for 45s at
    # capture_fps=30 would be ~1350 full-res JPEGs per camera in memory at
    # once. 2fps keeps memory bounded (45s * 2 = 90 frames/camera) while
    # still giving a usable clip.
    preroll_sample_interval_seconds: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
