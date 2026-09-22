import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


VerificationStatus = Literal["verified", "tampered", "signature_invalid", "not_signed", "file_missing"]


class EvidenceVerification(_CamelModel):
    """M25 tamper-evidence check result -- recomputes the file's SHA-256
    hash against what was captured and signed at upload time.

    - `verified`: hash and signature both match -- the file is byte-
      identical to what was captured, and the record wasn't altered since.
    - `tampered`: the file's bytes no longer match the hash captured at
      upload time.
    - `signature_invalid`: the stored hash/signature pair doesn't verify
      against this service's own key -- the database row itself was
      edited (e.g. the hash was swapped to match a modified file).
    - `not_signed`: no hash/signature was recorded for this evidence (it
      predates this feature) -- nothing to verify.
    - `file_missing`: the file is no longer on disk.

    `ledger_status` (M25 blockchain-style anchoring) is a second, independent
    opinion from ledger-service -- a separate database and signing key --
    on whether this hash is what was originally captured: `anchored`
    (agrees), `mismatch` (disagrees -- worth taking seriously even if
    `status` above says `verified`, since it means media-service's own
    records were changed to agree with themselves but not with the
    independent copy), `not_anchored`, or `unavailable`.
    """

    id: str
    status: VerificationStatus
    hash_matches: bool | None
    signature_valid: bool | None
    ledger_status: str | None = None
    checked_at: dt.datetime
