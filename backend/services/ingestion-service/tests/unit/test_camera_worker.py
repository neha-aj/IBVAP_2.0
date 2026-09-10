import time

import httpx
import redis.asyncio as redis

from app.core.config import Settings
from app.workers.camera_worker import CameraWorker


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _worker() -> CameraWorker:
    return CameraWorker(
        camera_id="CAM-01", camera_type="file", source_url="/videos/a.mp4",
        settings=_settings(), redis_client=redis.Redis(), http_client=httpx.AsyncClient(),
    )


def test_seconds_since_last_frame_starts_near_zero() -> None:
    """Set at construction (not only once the capture loop starts reading)
    so a worker that's slow to open isn't immediately misread as stuck."""
    worker = _worker()
    assert worker.seconds_since_last_frame() < 1.0


def test_seconds_since_last_frame_reflects_time_since_last_update() -> None:
    worker = _worker()
    worker._last_frame_at = time.monotonic() - 45.0
    assert worker.seconds_since_last_frame() >= 45.0


def test_default_modality_and_report_status_are_unchanged_from_before_m11() -> None:
    """Every existing single-stream camera constructs a CameraWorker without
    passing modality/report_status at all -- both must default to exactly
    the pre-M11 behavior (own cache slot keyed by camera_id, status
    reporting on)."""
    worker = _worker()
    assert worker._modality is None
    assert worker._should_report_status is True
    assert worker._cache_key == "CAM-01"


def test_dual_camera_thermal_worker_gets_its_own_cache_key_and_no_status_reporting() -> None:
    worker = CameraWorker(
        camera_id="CAM-DUAL-01", camera_type="dual", source_url="rtsp://thermal/stream",
        settings=_settings(), redis_client=redis.Redis(), http_client=httpx.AsyncClient(),
        modality="thermal", report_status=False,
    )
    assert worker._modality == "thermal"
    assert worker._should_report_status is False
    # Distinct from the RGB worker's cache slot ("CAM-DUAL-01") so the two
    # don't overwrite each other's live-preview frame.
    assert worker._cache_key == "CAM-DUAL-01:thermal"
    # The real camera id is preserved for status/correlation purposes even
    # though this worker is never the one that reports status.
    assert worker.camera_id == "CAM-DUAL-01"
