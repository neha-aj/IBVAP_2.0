"""Tamper-evident hashing and digital signatures for stored evidence files
(M25).

Every snapshot/recording is fingerprinted (SHA-256 over the exact bytes
written to disk) and the fingerprint is signed (Ed25519) at capture time.
A later verification can then prove two independent things:

- the file on disk is still byte-for-byte what was captured (the recomputed
  hash still matches the one taken at upload time), and
- the stored record itself wasn't quietly edited to match a different file
  (the signature -- which only this service's private key could have
  produced -- still matches the stored hash).

This is a lightweight instance of the same idea NI-7's protocol (hash +
sign + verify, see its docs/protocol.md) is built around, scoped to what
this service actually needs -- it is not a general-purpose crypto library
and makes no stronger claim than "this file/record pair is internally
consistent with what this service itself signed".

The signing key is generated once per deployment and persisted under
`{media_root}/.keys/` -- inside the same Docker volume media files already
live in, so it survives restarts without any new volume or config. It
never leaves this service. Losing it does not lose evidence, only the
ability to prove old records weren't retroactively altered; nothing about
reading or serving files depends on it.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

_KEY_SUBDIR = ".keys"
_KEY_FILENAME = "evidence_signing_key.raw"
_SIGN_PREFIX = b"NI7-EVIDENCE/1\0"


def compute_hash(data: bytes) -> str:
    """SHA-256 hex digest of the exact bytes stored on disk."""
    return hashlib.sha256(data).hexdigest()


def _signing_payload(*, record_id: str, camera_id: str, content_hash: str) -> bytes:
    """What the signature actually binds. Domain-separated (like every hash
    in NI-7's own MMR construction) so this signature can never be replayed
    as if it meant something else. Binding id+camera+hash together means a
    stored (hash, signature) pair can't be swapped onto a different file, a
    different camera, or a different record without invalidating it."""
    return _SIGN_PREFIX + f"{record_id}\0{camera_id}\0{content_hash}".encode()


@lru_cache
def _load_or_create_key(media_root: str) -> Ed25519PrivateKey:
    key_path = Path(media_root) / _KEY_SUBDIR / _KEY_FILENAME
    if key_path.exists():
        return Ed25519PrivateKey.from_private_bytes(key_path.read_bytes())

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    key_path.write_bytes(raw)
    try:
        key_path.chmod(0o600)  # best-effort; no-op on hosts that ignore POSIX perms
    except OSError:
        pass
    return key


def public_key_hex(media_root: str) -> str:
    """Non-secret verification key, exposed for anyone who wants to check a
    signature independently of this service (same spirit as NI-7's public-
    key registry entry -- not currently wired to an endpoint, kept simple
    until something actually needs it)."""
    return _load_or_create_key(media_root).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def current_key_id(media_root: str) -> str:
    """A short, stable, non-secret identifier for the key currently active
    at this `media_root` -- the first 16 hex chars of SHA-256(public key).
    Recorded alongside each signature purely as metadata (it is not part of
    the signed payload, so adding it here does not change, and cannot
    invalidate, any signature made before this existed).

    Only one key is ever active today, so `verify_signature` above always
    checks against *the* current key regardless of a record's stored
    `key_id` -- this is one-key-only in practice, but every future record
    is now self-describing about which key produced it, which is what a
    real rotation (multiple keys, chosen by this id) would need to key off
    without this ever needing to be retrofitted onto old rows."""
    public_key = _load_or_create_key(media_root).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(public_key).hexdigest()[:16]


def sign_evidence(*, media_root: str, record_id: str, camera_id: str, content_hash: str) -> str:
    """Hex-encoded Ed25519 signature over (record_id, camera_id, content_hash)."""
    key = _load_or_create_key(media_root)
    payload = _signing_payload(record_id=record_id, camera_id=camera_id, content_hash=content_hash)
    return key.sign(payload).hex()


def verify_signature(
    *, media_root: str, record_id: str, camera_id: str, content_hash: str, signature_hex: str
) -> bool:
    public_key = _load_or_create_key(media_root).public_key()
    payload = _signing_payload(record_id=record_id, camera_id=camera_id, content_hash=content_hash)
    try:
        public_key.verify(bytes.fromhex(signature_hex), payload)
        return True
    except (InvalidSignature, ValueError):
        return False
