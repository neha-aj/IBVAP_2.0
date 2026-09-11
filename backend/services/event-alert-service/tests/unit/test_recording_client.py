import base64

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


def _empty_preroll_response() -> httpx.Response:
    """Every pre-existing test in this file predates pre-roll -- their mock
    handlers only know about /snapshot and /media/recordings, so each one
    routes /recent-frames here to degrade to the old post-roll-only
    behavior (empty pre-roll) rather than breaking their own assertions."""
    return httpx.Response(200, json={"frames": []})


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
        if "/recent-frames" in str(request.url):
            return _empty_preroll_response()
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
        if "/recent-frames" in str(request.url):
            return _empty_preroll_response()
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


@pytest.mark.asyncio
async def test_capture_clip_includes_pre_roll_frames() -> None:
    """The evidence clip must actually include frames from *before* the
    trigger moment, not just post-roll -- otherwise pre-roll only exists on
    paper."""
    snapshot_calls = {"count": 0}
    recording_upload = {"file_frame_count": None}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/recent-frames" in url:
            frames = [
                {"timestamp": 1000.0, "jpeg": base64.b64encode(_jpeg_bytes()).decode("ascii")},
                {"timestamp": 1000.5, "jpeg": base64.b64encode(_jpeg_bytes()).decode("ascii")},
            ]
            return httpx.Response(200, json={"frames": frames})
        if "/snapshot" in url:
            snapshot_calls["count"] += 1
            return httpx.Response(200, content=_jpeg_bytes())
        assert "/media/recordings" in url
        # A real clip.webm was posted (non-empty) -- proves pre-roll frames
        # made it into the actual encoded video, not just fetched and
        # discarded. .webm, not .mp4: VP8/WebM (see recording_client.py's
        # own comment on why -- no browser-playable H.264 encoder is
        # available in this container, and MP4's mp4v fallback isn't
        # supported by any browser's <video> element).
        body = request.content
        recording_upload["has_body"] = b"clip.webm" in body or len(body) > 0
        return httpx.Response(201, json={"id": "rec-3", "url": "/media/recordings/CAM-01/clip.mp4"})

    client = _client(_settings(), handler)
    result = await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    assert result is not None
    assert snapshot_calls["count"] == 3  # post-roll unaffected by pre-roll
    assert recording_upload["has_body"]


@pytest.mark.asyncio
async def test_capture_clip_uses_earliest_pre_roll_timestamp_as_start_time() -> None:
    captured_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/recent-frames" in url:
            frames = [
                {"timestamp": 2000.0, "jpeg": base64.b64encode(_jpeg_bytes()).decode("ascii")},
                {"timestamp": 1990.0, "jpeg": base64.b64encode(_jpeg_bytes()).decode("ascii")},  # earliest
            ]
            return httpx.Response(200, json={"frames": frames})
        if "/snapshot" in url:
            return httpx.Response(200, content=_jpeg_bytes())
        captured_params.update(dict(request.url.params))
        return httpx.Response(201, json={"id": "rec-4", "url": "/media/recordings/x.mp4"})

    client = _client(_settings(), handler)
    await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    # 1990s since epoch, UTC -- the earlier of the two pre-roll timestamps,
    # not "now" (the old post-roll-only behavior) and not the later 2000s
    # entry.
    assert captured_params["start_time"].startswith("1970-01-01T00:33:10")


@pytest.mark.asyncio
async def test_capture_clip_degrades_gracefully_when_pre_roll_fetch_errors() -> None:
    """Same "never raises" contract as the rest of this client -- a broken
    pre-roll fetch (ingestion-service down, malformed response) must not
    prevent the (still valid) post-roll-only clip from being captured."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/recent-frames" in url:
            return httpx.Response(500)
        if "/snapshot" in url:
            return httpx.Response(200, content=_jpeg_bytes())
        return httpx.Response(201, json={"id": "rec-5", "url": "/media/recordings/x.mp4"})

    client = _client(_settings(), handler)
    result = await client.capture_clip(camera_id="CAM-01", event_id="evt-1")

    assert result is not None
