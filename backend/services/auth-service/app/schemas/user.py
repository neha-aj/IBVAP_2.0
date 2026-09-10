import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Role = Literal["admin", "operator", "viewer"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UserLogin(_CamelModel):
    username: str
    password: str


class UserRead(_CamelModel):
    id: uuid.UUID
    username: str
    role: Role
    is_active: bool = Field(default=True)


class UserCreate(_CamelModel):
    username: str
    password: str
    role: Role = "viewer"
