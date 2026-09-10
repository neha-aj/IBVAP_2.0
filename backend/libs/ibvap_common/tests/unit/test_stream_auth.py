import datetime as dt

import jwt
import pytest

from ibvap_common.errors import UnauthorizedError
from ibvap_common.settings import CommonSettings
from ibvap_common.stream_auth import build_resource_url, create_resource_token, verify_resource_token


def _settings() -> CommonSettings:
    return CommonSettings(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
    )


def test_valid_token_for_matching_resource_passes() -> None:
    settings = _settings()
    token = create_resource_token(resource="CAM-01", ttl_seconds=60, settings=settings)
    verify_resource_token(token, resource="CAM-01", settings=settings)  # must not raise


def test_missing_token_raises() -> None:
    with pytest.raises(UnauthorizedError):
        verify_resource_token(None, resource="CAM-01", settings=_settings())


def test_token_for_a_different_resource_is_rejected() -> None:
    settings = _settings()
    token = create_resource_token(resource="CAM-01", ttl_seconds=60, settings=settings)
    with pytest.raises(UnauthorizedError):
        verify_resource_token(token, resource="CAM-02", settings=settings)


def test_expired_token_is_rejected() -> None:
    settings = _settings()
    token = create_resource_token(resource="CAM-01", ttl_seconds=-1, settings=settings)
    with pytest.raises(UnauthorizedError):
        verify_resource_token(token, resource="CAM-01", settings=settings)


def test_token_signed_with_a_different_secret_is_rejected() -> None:
    settings = _settings()
    other_settings = CommonSettings(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="a-different-secret",
    )
    token = create_resource_token(resource="CAM-01", ttl_seconds=60, settings=other_settings)
    with pytest.raises(UnauthorizedError):
        verify_resource_token(token, resource="CAM-01", settings=settings)


def test_an_ordinary_access_token_is_not_accepted_as_a_stream_token() -> None:
    """A login access token (auth.py's own shape: sub/username/role/type=
    "access") must not double as a stream token just because it's a valid
    JWT signed with the same secret -- `type` has to be exactly "resource"."""
    settings = _settings()
    now = dt.datetime.now(dt.UTC)
    access_token = jwt.encode(
        {
            "sub": "u1", "username": "alice", "role": "viewer", "type": "access",
            "iat": int(now.timestamp()), "exp": int((now + dt.timedelta(minutes=1)).timestamp()),
        },
        settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(UnauthorizedError):
        verify_resource_token(access_token, resource="CAM-01", settings=settings)


def test_build_resource_url_appends_a_token_that_verifies_for_that_resource() -> None:
    """M24 security review follow-up (`GET /media/snapshots/{id}`): the
    shared URL-building helper anpr-service/reid-service/event-alert-
    service/media-service all use to hand out a fetchable, token-scoped
    URL rather than a bare id."""
    settings = _settings()
    url = build_resource_url(path="/media/snapshots/SNAP-1", resource="SNAP-1", settings=settings)

    assert url.startswith("/media/snapshots/SNAP-1?token=")
    token = url.split("?token=", 1)[1]
    verify_resource_token(token, resource="SNAP-1", settings=settings)  # must not raise


def test_build_resource_url_token_is_scoped_to_its_own_resource_only() -> None:
    settings = _settings()
    url = build_resource_url(path="/media/snapshots/SNAP-1", resource="SNAP-1", settings=settings)
    token = url.split("?token=", 1)[1]

    with pytest.raises(UnauthorizedError):
        verify_resource_token(token, resource="SNAP-2", settings=settings)
