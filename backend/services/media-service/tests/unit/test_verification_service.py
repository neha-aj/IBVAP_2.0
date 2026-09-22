import pytest

from app.core.config import Settings
from app.security import integrity
from app.services.verification_service import verify_evidence


@pytest.fixture(autouse=True)
def _clear_key_cache():
    yield
    integrity._load_or_create_key.cache_clear()


def _settings(tmp_path) -> Settings:
    return Settings(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s", media_root=str(tmp_path),
        # Unroutable on purpose -- these tests exercise media-service's own
        # hash/signature logic, not ledger-service; a fast, guaranteed-
        # unreachable address keeps `ledger_status` a quick "unavailable"
        # instead of a real network attempt or DNS lookup.
        ledger_service_url="http://127.0.0.1:1", ledger_request_timeout_seconds=0.5,
    )


def _write_file(settings: Settings, relative: str, data: bytes) -> str:
    path = tmp_path_file(settings, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"{settings.media_url_prefix}/{relative}"


def tmp_path_file(settings: Settings, relative: str):
    from pathlib import Path

    return Path(settings.media_root) / relative


def _sign(settings: Settings, *, record_id: str, camera_id: str, data: bytes) -> str:
    content_hash = integrity.compute_hash(data)
    return integrity.sign_evidence(
        media_root=settings.media_root, record_id=record_id, camera_id=camera_id, content_hash=content_hash
    ), content_hash


async def test_an_untouched_file_verifies(tmp_path) -> None:
    settings = _settings(tmp_path)
    data = b"real evidence bytes"
    signature, content_hash = _sign(settings, record_id="rec-1", camera_id="CAM-01", data=data)
    file_path = _write_file(settings, "recordings/CAM-01/clip.webm", data)

    result = await verify_evidence(
        record_type="recording", record_id="rec-1", camera_id="CAM-01", file_path=file_path,
        content_hash=content_hash, signature=signature, settings=settings,
    )

    assert result.status == "verified"
    assert result.hash_matches is True
    assert result.signature_valid is True
    assert result.ledger_status == "unavailable"


async def test_a_modified_file_is_reported_as_tampered(tmp_path) -> None:
    settings = _settings(tmp_path)
    original = b"real evidence bytes"
    signature, content_hash = _sign(settings, record_id="rec-1", camera_id="CAM-01", data=original)
    file_path = _write_file(settings, "recordings/CAM-01/clip.webm", original)
    # Overwrite the file after it was captured/signed -- the tamper case.
    tmp_path_file(settings, "recordings/CAM-01/clip.webm").write_bytes(b"altered bytes")

    result = await verify_evidence(
        record_type="recording", record_id="rec-1", camera_id="CAM-01", file_path=file_path,
        content_hash=content_hash, signature=signature, settings=settings,
    )

    assert result.status == "tampered"
    assert result.hash_matches is False
    assert result.signature_valid is True  # the signature itself is still genuine


async def test_a_hash_edited_in_the_database_is_reported_as_signature_invalid(tmp_path) -> None:
    """Simulates someone editing the stored content_hash (e.g. to match a
    swapped-in file) without access to the private key."""
    settings = _settings(tmp_path)
    data = b"real evidence bytes"
    signature, _real_hash = _sign(settings, record_id="rec-1", camera_id="CAM-01", data=data)
    file_path = _write_file(settings, "recordings/CAM-01/clip.webm", data)
    forged_hash = integrity.compute_hash(b"whatever the forger wants")

    result = await verify_evidence(
        record_type="recording", record_id="rec-1", camera_id="CAM-01", file_path=file_path,
        content_hash=forged_hash, signature=signature, settings=settings,
    )

    assert result.status == "signature_invalid"
    assert result.signature_valid is False


async def test_a_record_with_no_hash_or_signature_is_not_signed(tmp_path) -> None:
    settings = _settings(tmp_path)
    file_path = _write_file(settings, "recordings/CAM-01/clip.webm", b"pre-M25 evidence")

    result = await verify_evidence(
        record_type="recording", record_id="rec-1", camera_id="CAM-01", file_path=file_path,
        content_hash=None, signature=None, settings=settings,
    )

    assert result.status == "not_signed"
    assert result.hash_matches is None
    assert result.signature_valid is None
    # Nothing to check against the ledger when there was never a hash to anchor.
    assert result.ledger_status is None


async def test_a_deleted_file_is_reported_as_file_missing(tmp_path) -> None:
    settings = _settings(tmp_path)
    data = b"real evidence bytes"
    signature, content_hash = _sign(settings, record_id="rec-1", camera_id="CAM-01", data=data)

    result = await verify_evidence(
        record_type="recording", record_id="rec-1", camera_id="CAM-01",
        file_path=f"{settings.media_url_prefix}/recordings/CAM-01/never-written.webm",
        content_hash=content_hash, signature=signature, settings=settings,
    )

    assert result.status == "file_missing"
