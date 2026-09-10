from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "analytics-service"
    db_schema: str = "analytics"

    camera_service_url: str = "http://camera-service:8000"

    # SAS §5: "REFRESH MATERIALIZED VIEW CONCURRENTLY on a cron (e.g. every
    # 60s)". Concurrent refresh needs a unique index per view (added in the
    # migration) so it can run without blocking reads.
    refresh_interval_seconds: int = 60

    # SAS: "Redis (cached aggregates, short TTL)" -- an extra cache layer in
    # front of the already-fast materialized-view reads, so a burst of
    # Dashboard polls from many browser tabs doesn't even hit Postgres.
    cache_ttl_seconds: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
