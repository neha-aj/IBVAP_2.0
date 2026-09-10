from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "auth-service"
    db_schema: str = "auth"

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "change_me_admin_password"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
