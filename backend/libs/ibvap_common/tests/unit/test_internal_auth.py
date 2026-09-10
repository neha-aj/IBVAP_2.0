import pytest

from ibvap_common.errors import UnauthorizedError
from ibvap_common.internal_auth import verify_internal_token
from ibvap_common.settings import CommonSettings


def _settings() -> CommonSettings:
    return CommonSettings(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
        internal_service_token="the-real-token",
    )


def test_correct_token_passes() -> None:
    verify_internal_token("the-real-token", _settings())  # must not raise


def test_missing_token_raises() -> None:
    with pytest.raises(UnauthorizedError):
        verify_internal_token(None, _settings())


def test_wrong_token_raises() -> None:
    with pytest.raises(UnauthorizedError):
        verify_internal_token("not-the-token", _settings())
