"""Ledger-service's own Ed25519 signing key -- deliberately separate from
media-service's key (app/security/integrity.py there). The whole point of
an independent anchor is that it isn't verifiable by, or forgeable with,
the same key as the thing it's anchoring; sharing a key would collapse
that independence back down to "one more copy of the same secret"."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

_KEY_SUBDIR = ".keys"
_KEY_FILENAME = "ledger_signing_key.raw"


@lru_cache
def _load_or_create_key(key_root: str) -> Ed25519PrivateKey:
    key_path = Path(key_root) / _KEY_SUBDIR / _KEY_FILENAME
    if key_path.exists():
        return Ed25519PrivateKey.from_private_bytes(key_path.read_bytes())

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    key_path.write_bytes(raw)
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return key


def sign_entry_hash(*, key_root: str, entry_hash: str) -> str:
    key = _load_or_create_key(key_root)
    return key.sign(bytes.fromhex(entry_hash)).hex()
