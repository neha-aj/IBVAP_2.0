"""Base settings every service extends.

Each service defines its own `Settings(CommonSettings)` in `app/core/config.py`
and adds service-specific fields (e.g. DB_SCHEMA). Values are sourced from
environment variables (12-factor), matching the docker-compose environment
blocks in the root `docker-compose.yml`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "ibvap-service"

    # --- Postgres ---
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    db_schema: str = "public"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379

    # --- Auth ---
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- Service-to-service (M2M) auth ---
    # Shared secret used between internal services (e.g. Ingestion -> Camera
    # Management) for calls that aren't made on behalf of a logged-in user.
    # Phase 1 uses a shared secret; mTLS is the production hardening path (SAS §12).
    internal_service_token: str = "change-me-internal-token"

    # --- Resource-scoped stream tokens (M24 security hardening) ---
    # How long a signed `?token=` on a URL like `/stream/{camera_id}/mjpeg`
    # stays valid -- only needs to survive from "camera-service issues the
    # URL" to "the browser's <img> opens the connection" (near-instant in
    # practice), not the lifetime of the stream itself: MJPEG auth is
    # checked once at connection time, not per frame, so an already-open
    # stream keeps flowing past this window.
    stream_token_ttl_seconds: int = 300

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_common_settings() -> CommonSettings:
    return CommonSettings()  # type: ignore[call-arg]  # values come from env
