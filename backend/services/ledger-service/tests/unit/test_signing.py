import pytest

from app.security import signing


@pytest.fixture(autouse=True)
def _clear_key_cache():
    yield
    signing._load_or_create_key.cache_clear()


def test_a_signed_entry_hash_verifies_with_the_same_key(tmp_path) -> None:
    key_root = str(tmp_path)
    entry_hash = "a" * 64
    signature = signing.sign_entry_hash(key_root=key_root, entry_hash=entry_hash)

    key = signing._load_or_create_key(key_root)
    key.public_key().verify(bytes.fromhex(signature), bytes.fromhex(entry_hash))  # must not raise


def test_the_signing_key_persists_across_separate_loads(tmp_path) -> None:
    key_root = str(tmp_path)
    entry_hash = "b" * 64
    signature = signing.sign_entry_hash(key_root=key_root, entry_hash=entry_hash)

    signing._load_or_create_key.cache_clear()  # simulate a fresh process

    key = signing._load_or_create_key(key_root)
    key.public_key().verify(bytes.fromhex(signature), bytes.fromhex(entry_hash))  # must not raise


def test_two_different_key_roots_get_independent_keys(tmp_path) -> None:
    root_a, root_b = str(tmp_path / "a"), str(tmp_path / "b")
    entry_hash = "c" * 64
    signature = signing.sign_entry_hash(key_root=root_a, entry_hash=entry_hash)

    key_b = signing._load_or_create_key(root_b)
    from cryptography.exceptions import InvalidSignature

    with pytest.raises(InvalidSignature):
        key_b.public_key().verify(bytes.fromhex(signature), bytes.fromhex(entry_hash))
