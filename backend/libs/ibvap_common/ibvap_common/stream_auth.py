"""Short-lived, resource-scoped signed tokens for endpoints that must be
embeddable in a plain URL (e.g. `<img src="...">` for the MJPEG preview
stream) and therefore can't carry an `Authorization: Bearer ...` header the
way every other authenticated request does (M24 security review: this gap
is exactly how `GET /stream/{camera_id}/mjpeg` ended up reachable with zero
auth even though the endpoint that hands out its URL, `GET /cameras/{id}/
stream`, is correctly gated by `require_role`).

Reuses `Settings.jwt_secret`/`jwt_algorithm` -- the same trust root as
login-issued access tokens -- rather than provisioning a second secret;
this is a different *token shape* (resource-scoped, no user identity), not
a different trust root, so `auth.py`'s `TokenPayload`/`decode_token` (which
require `sub`/`username`/`role`) don't fit and aren't reused directly.
"""

from __future__ import annotations

import datetime as dt

import jwt

from ibvap_common.errors import UnauthorizedError
from ibvap_common.settings import CommonSettings

_TOKEN_TYPE = "resource"


def create_resource_token(*, resource: str, ttl_seconds: int, settings: CommonSettings) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "res": resource,
        "type": _TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_resource_token(token: str | None, *, resource: str, settings: CommonSettings) -> None:
    """Raises `UnauthorizedError` unless `token` is a valid, unexpired token
    minted for this exact `resource` string."""
    if not token:
        raise UnauthorizedError("Missing stream token")
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Stream token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid stream token") from exc
    if raw.get("type") != _TOKEN_TYPE or raw.get("res") != resource:
        raise UnauthorizedError("Invalid stream token")


def build_resource_url(*, path: str, resource: str, settings: CommonSettings) -> str:
    """Mints a fresh resource token scoped to `resource` and appends it to
    `path` as `?token=...` -- the shape every issuing endpoint (anpr-service's
    `GET /reads`, reid-service's search/matches endpoints, event-alert-
    service's event/alert detail endpoints, media-service's own recording
    playback URL) hands to the frontend for an `<img>`/`<video>` `src` it
    can't attach an `Authorization` header to.

    Minted fresh on every call (not cached alongside the resource itself):
    unlike the mjpeg case, these URLs are often viewed long after creation
    (browsing an old event/alert), so a token baked in once at write time
    would already be expired by then -- `Settings.stream_token_ttl_seconds`
    only needs to outlive one page view, not the resource's lifetime."""
    token = create_resource_token(resource=resource, ttl_seconds=settings.stream_token_ttl_seconds, settings=settings)
    return f"{path}?token={token}"
