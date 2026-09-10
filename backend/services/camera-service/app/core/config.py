from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "camera-service"
    db_schema: str = "camera"

    max_upload_size_bytes: int = 2 * 1024 * 1024 * 1024  # 2GB, matches nginx client_max_body_size

    # Phase 2 M23: uploaded source videos are now proxied to Media Service
    # instead of written directly via this service's own (now-retired)
    # `LocalStorageBackend`.
    media_service_url: str = "http://media-service:8000"
    # Generous -- forwarding a large source video, not a quick metadata call.
    media_upload_timeout_seconds: float = 60.0
    # Phase 2 M23: `GET /cameras/{id}/snapshot`, the public counterpart to
    # Ingestion Service's own internal-only snapshot route.
    ingestion_service_url: str = "http://ingestion-service:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
