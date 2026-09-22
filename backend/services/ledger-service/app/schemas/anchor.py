import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AnchorRequest(_CamelModel):
    record_type: str
    record_id: str
    content_hash: str


class AnchorRead(_CamelModel):
    id: str
    entry_hash: str
    signature: str
    created_at: dt.datetime


LedgerStatus = Literal["anchored", "not_anchored", "mismatch"]


class LedgerVerification(_CamelModel):
    status: LedgerStatus
    entry_hash: str | None = None
    anchored_at: dt.datetime | None = None


class ChainIntegrity(_CamelModel):
    intact: bool
    entries_checked: int
    first_broken_entry_id: str | None
