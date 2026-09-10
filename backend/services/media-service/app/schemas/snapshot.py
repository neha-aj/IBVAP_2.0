from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SnapshotCreated(_CamelModel):
    """API Spec §6: `POST /media/snapshots` returns `{id, url}`."""

    id: str
    url: str
