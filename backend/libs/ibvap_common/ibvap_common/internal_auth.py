"""Service-to-service (M2M) authentication for internal-only endpoints, e.g.
Stream Ingestion Service reading camera configs / pushing status updates to
the Camera Management Service. Distinct from `auth.py`'s user JWTs -- these
calls aren't made on behalf of a logged-in operator (SAS §8, §12).
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header

from ibvap_common.errors import UnauthorizedError
from ibvap_common.settings import CommonSettings, get_common_settings


def verify_internal_token(
    x_internal_token: str | None = Header(default=None),
    settings: CommonSettings = Depends(get_common_settings),
) -> None:
    # Constant-time comparison -- `!=` on strings short-circuits at the
    # first differing byte, which (in principle) leaks how many leading
    # characters of a guess were correct via response timing.
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_service_token):
        raise UnauthorizedError("Missing or invalid internal service token")
