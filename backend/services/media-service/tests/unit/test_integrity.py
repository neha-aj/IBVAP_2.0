import pytest

from app.security import integrity


@pytest.fixture(autouse=True)
def _clear_key_cache():
    """Each test gets its own tmp `media_root`, but `_load_or_create_key` is
    `lru_cache`d by that path string, so an isolated cache per test isn't
    otherwise needed -- this just keeps the cache from growing unbounded
    across the whole test session."""
    yield
    integrity._load_or_create_key.cache_clear()


def test_the_same_bytes_always_hash_the_same_way(tmp_path) -> None:
    assert integrity.compute_hash(b"evidence") == integrity.compute_hash(b"evidence")


def test_different_bytes_hash_differently(tmp_path) -> None:
    assert integrity.compute_hash(b"evidence") != integrity.compute_hash(b"tampered")


def test_a_signature_verifies_against_the_exact_record_it_was_made_for(tmp_path) -> None:
    root = str(tmp_path)
    content_hash = integrity.compute_hash(b"evidence")
    signature = integrity.sign_evidence(media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash)

    assert integrity.verify_signature(
        media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash, signature_hex=signature
    )


def test_a_signature_fails_if_the_recorded_hash_was_swapped(tmp_path) -> None:
    """Simulates someone editing the DB row to match a different (tampered)
    file's hash, without the private key: the old signature no longer
    covers the new hash."""
    root = str(tmp_path)
    original_hash = integrity.compute_hash(b"evidence")
    signature = integrity.sign_evidence(
        media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=original_hash
    )
    tampered_hash = integrity.compute_hash(b"tampered")

    assert not integrity.verify_signature(
        media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=tampered_hash, signature_hex=signature
    )


def test_a_signature_fails_if_the_record_id_was_swapped(tmp_path) -> None:
    root = str(tmp_path)
    content_hash = integrity.compute_hash(b"evidence")
    signature = integrity.sign_evidence(media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash)

    assert not integrity.verify_signature(
        media_root=root, record_id="rec-2", camera_id="CAM-01", content_hash=content_hash, signature_hex=signature
    )


def test_a_malformed_signature_fails_closed_instead_of_raising(tmp_path) -> None:
    root = str(tmp_path)
    content_hash = integrity.compute_hash(b"evidence")

    assert not integrity.verify_signature(
        media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash, signature_hex="not-hex!!"
    )


def test_the_signing_key_persists_across_separate_loads(tmp_path) -> None:
    """A signature made with one 'process' (cache cleared in between, as a
    real restart would) must still verify -- the key is read back from disk,
    not regenerated."""
    root = str(tmp_path)
    content_hash = integrity.compute_hash(b"evidence")
    signature = integrity.sign_evidence(media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash)

    integrity._load_or_create_key.cache_clear()  # simulate a fresh process reading the same media_root

    assert integrity.verify_signature(
        media_root=root, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash, signature_hex=signature
    )


def test_two_different_media_roots_get_independent_keys(tmp_path) -> None:
    root_a, root_b = str(tmp_path / "a"), str(tmp_path / "b")
    content_hash = integrity.compute_hash(b"evidence")
    signature = integrity.sign_evidence(media_root=root_a, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash)

    assert not integrity.verify_signature(
        media_root=root_b, record_id="rec-1", camera_id="CAM-01", content_hash=content_hash, signature_hex=signature
    )
