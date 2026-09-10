import uuid

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SectorRead(_CamelModel):
    id: uuid.UUID
    name: str
    code: str


class SectorCreate(_CamelModel):
    name: str
    code: str
