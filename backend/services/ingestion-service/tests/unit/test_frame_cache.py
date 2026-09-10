import pytest

from app.preview.frame_cache import FrameCache


@pytest.mark.asyncio
async def test_set_and_get_roundtrip() -> None:
    cache = FrameCache()
    await cache.set("CAM-01", b"jpegbytes")
    assert await cache.get("CAM-01") == b"jpegbytes"


@pytest.mark.asyncio
async def test_get_missing_camera_returns_none() -> None:
    cache = FrameCache()
    assert await cache.get("UNKNOWN") is None


@pytest.mark.asyncio
async def test_clear_removes_entry() -> None:
    cache = FrameCache()
    await cache.set("CAM-01", b"jpegbytes")
    await cache.clear("CAM-01")
    assert await cache.get("CAM-01") is None
