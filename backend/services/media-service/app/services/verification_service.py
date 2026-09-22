"""Ties the stored hash/signature (app/security/integrity.py) to an actual
file on disk and produces the API-facing EvidenceVerification result. Kept
separate from app/security/integrity.py so the crypto primitives stay
unit-testable without filesystem/pydantic concerns mixed in."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.core.config import Settings
from app.schemas.verification import EvidenceVerification
from app.security import integrity
from app.services import ledger_service


def _disk_path(file_path: str, settings: Settings) -> Path:
    prefix = settings.media_url_prefix.rstrip("/")
    if file_path.startswith(prefix + "/"):
        return Path(settings.media_root) / file_path[len(prefix) + 1 :]
    # Already a raw filesystem path (only possible if url_prefix were None
    # at save time, which snapshots/recordings never do) -- kept literal
    # rather than guessed, so this never silently mis-resolves a path.
    return Path(file_path)


async def verify_evidence(
    *,
    record_type: str,
    record_id: str,
    camera_id: str,
    file_path: str,
    content_hash: str | None,
    signature: str | None,
    settings: Settings,
) -> EvidenceVerification:
    now = dt.datetime.now(dt.UTC)

    if content_hash is None or signature is None:
        return EvidenceVerification(
            id=record_id, status="not_signed", hash_matches=None, signature_valid=None, checked_at=now
        )

    disk_path = _disk_path(file_path, settings)
    if not disk_path.is_file():
        return EvidenceVerification(
            id=record_id, status="file_missing", hash_matches=None, signature_valid=None, checked_at=now
        )

    current_hash = integrity.compute_hash(disk_path.read_bytes())
    hash_matches = current_hash == content_hash
    # Verified against the *stored* hash, not the recomputed one: the
    # signature proves this hash was genuinely produced by this service at
    # capture time, independent of whether the file has since changed --
    # that's what lets `tampered` (file changed, signature still valid)
    # and `signature_invalid` (record itself edited) mean different things.
    signature_valid = integrity.verify_signature(
        media_root=settings.media_root,
        record_id=record_id,
        camera_id=camera_id,
        content_hash=content_hash,
        signature_hex=signature,
    )

    if not signature_valid:
        status = "signature_invalid"
    elif not hash_matches:
        status = "tampered"
    else:
        status = "verified"

    # M25: a second, independently-keyed opinion on the *stored* hash (same
    # reasoning as checking against the stored hash for the signature above,
    # not the recomputed one -- this asks "does the outside world agree
    # with what media-service says it originally captured", not "does the
    # file match today").
    ledger_status = await ledger_service.verify(
        record_type=record_type, record_id=record_id, content_hash=content_hash, settings=settings
    )

    return EvidenceVerification(
        id=record_id, status=status, hash_matches=hash_matches, signature_valid=signature_valid,
        ledger_status=ledger_status, checked_at=now,
    )
