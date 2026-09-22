from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    """M25 blockchain-style anchoring: an independent, append-only,
    hash-chained ledger. It has its own signing key (separate from
    media-service's own) and, although it shares the same Postgres server
    as every other service in this dev deployment, it owns its own schema
    and is the one service media-service never has direct DB access to --
    the point is that anchoring here survives a compromise of
    media-service's own database *and* its signing key, not that this is
    physically separate infrastructure (a real deployment would put this
    on genuinely separate infrastructure, or a real distributed ledger)."""

    service_name: str = "ledger-service"
    db_schema: str = "ledger"

    ledger_key_root: str = "/data/ledger"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
