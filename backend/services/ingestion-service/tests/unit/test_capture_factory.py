"""These tests import app.capture.factory, which pulls in OpenCV -- run
`pip install -e ".[dev]"` in this service (installs the full dependency set,
including opencv-python-headless) before running pytest here."""

import pytest

from ibvap_common.errors import ApiError

from app.capture.factory import build_frame_source
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s"
    )


def test_file_source_without_upload_raises() -> None:
    with pytest.raises(ApiError):
        build_frame_source(camera_type="file", source_url=None, settings=_settings())


def test_webcam_source_without_device_raises() -> None:
    with pytest.raises(ApiError):
        build_frame_source(camera_type="webcam", source_url=None, settings=_settings())


def test_unsupported_type_raises() -> None:
    with pytest.raises(ApiError):
        build_frame_source(camera_type="drone", source_url="whatever", settings=_settings())


def test_file_source_with_path_builds_ok() -> None:
    source = build_frame_source(camera_type="file", source_url="/tmp/video.mp4", settings=_settings())
    assert source is not None


def test_file_source_seeds_loop_generation_from_argument() -> None:
    source = build_frame_source(
        camera_type="file", source_url="/tmp/video.mp4", settings=_settings(), initial_generation=7
    )
    assert source.loop_generation == 7


def test_thermal_source_without_url_raises() -> None:
    with pytest.raises(ApiError):
        build_frame_source(camera_type="thermal", source_url=None, settings=_settings())


def test_thermal_source_with_url_builds_ok() -> None:
    source = build_frame_source(camera_type="thermal", source_url="rtsp://thermal-cam/stream", settings=_settings())
    assert source is not None


def test_dual_source_without_url_raises() -> None:
    """`build_frame_source` opens one stream at a time -- for a 'dual'
    camera, WorkerManager calls this twice (once per modality's own URL);
    this only checks that whichever URL is missing fails the same way
    rtsp/ip already do, not the two-worker orchestration itself (see
    test_worker_manager.py for that)."""
    with pytest.raises(ApiError):
        build_frame_source(camera_type="dual", source_url=None, settings=_settings())


def test_dual_source_with_url_builds_ok() -> None:
    source = build_frame_source(camera_type="dual", source_url="rtsp://rgb-cam/stream", settings=_settings())
    assert source is not None
