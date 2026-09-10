from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.user import UserRead


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TokenPair(_CamelModel):
    access_token: str
    refresh_token: str
    user: UserRead


class RefreshRequest(_CamelModel):
    refresh_token: str
