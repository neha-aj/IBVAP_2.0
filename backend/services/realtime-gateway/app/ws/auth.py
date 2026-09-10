"""Per-connection auth (SAS §8: "WebSocket connections authenticate via
token in the connection handshake... validated once at connect"). Every
role (viewer and up) can subscribe -- everything pushed over this gateway
is already gated read-only data at its REST source, so there's no
additional per-topic role check beyond "this is a valid, unexpired access
token"."""

from __future__ import annotations

from ibvap_common.auth import TokenPayload, decode_token
from ibvap_common.errors import UnauthorizedError
from ibvap_common.settings import CommonSettings


def authenticate(token: str | None, settings: CommonSettings) -> TokenPayload:
    if not token:
        raise UnauthorizedError("Missing token query parameter")
    payload = decode_token(token, settings)
    if payload.type != "access":
        raise UnauthorizedError("An access token is required")
    return payload
