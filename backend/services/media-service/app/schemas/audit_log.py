import datetime as dt

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuditLogEntryRead(_CamelModel):
    id: str
    record_type: str
    record_id: str
    action: str
    actor: str | None
    result: str | None
    entry_hash: str
    created_at: dt.datetime


class AuditLogRead(_CamelModel):
    record_type: str
    record_id: str
    entries: list[AuditLogEntryRead]


class ChainIntegrity(_CamelModel):
    intact: bool
    entries_checked: int
    first_broken_entry_id: str | None
