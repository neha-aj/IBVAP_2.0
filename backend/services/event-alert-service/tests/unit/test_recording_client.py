import httpx
import numpy as np
import pytest

from app.core.config import Settings
from app.streaming.recording_client import RecordingClient


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "recording_post_roll_frame_count": 3,
        "recording_post_roll_interval_seconds": 0.0, "recording_clip_fps": 5.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _jpeg_bytes(height: int = 40, width: int = 40) -> bytes:
    import cv2
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def _client(settings: Settings, handler) -> RecordingClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return RecordingClient(http_client, settings)


@pytest.mark.asyncio
async def test_capture_clip_returns_none_when_camera_never_streams() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(_settings(), handler)
    result = await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    assert result is None


@pytest.mark.asyncio
async def test_capture_clip_uploads_and_returns_id_url_on_success() -> None:
    snapshot_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/snapshot" in str(request.url):
            snapshot_calls["count"] += 1
            return httpx.Response(200, content=_jpeg_bytes())
        assert "/media/recordings" in str(request.url)
        return httpx.Response(201, json={"id": "rec-1", "url": "/media/recordings/CAM-01/clip.mp4"})

    client = _client(_settings(), handler)
    result = await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    assert snapshot_calls["count"] == 3  # recording_post_roll_frame_count
    assert result is not None
    assert result.id == "rec-1"
    assert result.url == "/media/recordings/CAM-01/clip.mp4"


@pytest.mark.asyncio
async def test_capture_clip_tolerates_some_missed_frames() -> None:
    """A camera that drops out for one tick mid-capture must not abort the
    whole clip -- whatever frames were collected still get encoded."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/snapshot" in str(request.url):
            calls["count"] += 1
            if calls["count"] == 2:
                return httpx.Response(404)
            return httpx.Response(200, content=_jpeg_bytes())
        return httpx.Response(201, json={"id": "rec-2", "url": "/media/recordings/x.mp4"})

    client = _client(_settings(), handler)
    result = await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    assert result is not None  # 2 of 3 frames still succeeded


@pytest.mark.asyncio
async def test_capture_clip_returns_none_when_upload_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/snapshot" in str(request.url):
            return httpx.Response(200, content=_jpeg_bytes())
        return httpx.Response(500)

    client = _client(_settings(), handler)
    result = await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    assert result is None
