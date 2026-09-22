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
    # M25 MFA: required only once the user has enabled it (see AuthService.
    # login) -- every login for an account without MFA ignores this field
    # entirely, so it's optional and additive.
    totp_code: str | None = None


class UserRead(_CamelModel):
    id: uuid.UUID
    username: str
    role: Role
    is_active: bool = Field(default=True)
    mfa_enabled: bool = Field(default=False)


class UserCreate(_CamelModel):
    username: str
    password: str
    role: Role = "viewer"


class MfaEnrollResponse(_CamelModel):
    """`secret` is shown once for manual entry into an authenticator app
    (no QR-code rendering added here -- keeps this change frontend-library-
    free; `provisioning_uri` is included so a QR code can be added later
    without another API change)."""

    secret: str
    provisioning_uri: str


class MfaVerifyRequest(_CamelModel):
    code: str


class MfaStatus(_CamelModel):
    enabled: bool
