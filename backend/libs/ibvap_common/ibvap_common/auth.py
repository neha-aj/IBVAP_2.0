"""Stateless JWT validation + RBAC dependency, shared by every service.

Only the Auth Service issues tokens (see auth-service/app/services/auth_service.py).
Every other service validates the token's signature/expiry/role locally --
no per-request call back to the Auth Service is needed (API Spec §11 RBAC matrix).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

import jwt
from fastapi import Depends, Header
from pydantic import BaseModel

from ibvap_common.errors import ForbiddenError, UnauthorizedError
from ibvap_common.settings import CommonSettings, get_common_settings

Role = Literal["admin", "operator", "viewer"]

ROLE_HIERARCHY: dict[Role, int] = {"viewer": 0, "operator": 1, "admin": 2}


class TokenPayload(BaseModel):
    sub: str  # user id
    username: str
    role: Role
    exp: int
    type: Literal["access", "refresh"]


def create_token(
    *,
    user_id: str,
    username: str,
    role: Role,
    token_type: Literal["access", "refresh"],
    settings: CommonSettings,
) -> str:
    now = dt.datetime.now(dt.UTC)
    if token_type == "access":
        expire = now + dt.timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expire = now + dt.timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        # Ensures uniqueness even when two tokens are minted within the same
        # wall-clock second (e.g. login immediately followed by refresh) --
        # without this, iat/exp/sub/etc are all identical and the encoded
        # JWT collides byte-for-byte.
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: CommonSettings) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc
    return TokenPayload(**raw)


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: CommonSettings = Depends(get_common_settings),
) -> TokenPayload:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token, settings)
    if payload.type != "access":
        raise UnauthorizedError("An access token is required")
    return payload


def require_role(minimum_role: Role):
    """Dependency factory: `Depends(require_role("operator"))`."""

    def _dependency(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if ROLE_HIERARCHY[user.role] < ROLE_HIERARCHY[minimum_role]:
            raise ForbiddenError(
                f"Requires role '{minimum_role}' or higher, has '{user.role}'"
            )
        return user

    return _dependency
