from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.user import UserRead


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TokenPair(_CamelModel):
    """Internal shape -- what AuthService itself returns. The route layer
    never sends `refresh_token` on to the browser as JSON (see
    `LoginResponse` below); it sets it as an httpOnly cookie instead, so a
    successful XSS on the frontend can't read it out of a JS-visible
    response body or storage."""

    access_token: str
    refresh_token: str
    user: UserRead


class LoginResponse(_CamelModel):
    """What actually goes back to the browser from /login and /refresh --
    the access token (short-lived, meant to be readable by JS since it has
    to go in an Authorization header) and the user, nothing else."""

    access_token: str
    user: UserRead
