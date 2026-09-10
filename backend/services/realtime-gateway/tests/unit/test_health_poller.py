import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.streaming.health_poller import HealthPoller


def _settings(**overrides) -> Settings:
    defaults = dict(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
        monitored_services=["svc-a", "svc-b"],
    )
    defaults.update(overrides)
    return Settings(**defaults)


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel: str, data: str) -> None:
        self.published.append((channel, json.loads(data)))


def _poller(settings: Settings, handler, redis_client=None) -> HealthPoller:
    poller = HealthPoller(redis_client or FakeRedis(), settings)
    poller._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return poller


@pytest.mark.asyncio
async def test_first_check_publishes_initial_status_for_every_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    redis_client = FakeRedis()
    poller = _poller(_settings(), handler, redis_client)

    await poller._check_one("svc-a")
    await poller._check_one("svc-b")

    assert redis_client.published == [
        ("system.health", {"service": "svc-a", "status": "up"}),
        ("system.health", {"service": "svc-b", "status": "up"}),
    ]


@pytest.mark.asyncio
async def test_unchanged_status_does_not_republish() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    redis_client = FakeRedis()
    poller = _poller(_settings(), handler, redis_client)

    await poller._check_one("svc-a")
    await poller._check_one("svc-a")
    await poller._check_one("svc-a")

    assert len(redis_client.published) == 1


@pytest.mark.asyncio
async def test_status_transition_up_to_down_publishes_again() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200)
        return httpx.Response(503)

    redis_client = FakeRedis()
    poller = _poller(_settings(), handler, redis_client)

    await poller._check_one("svc-a")
    await poller._check_one("svc-a")

    assert redis_client.published == [
        ("system.health", {"service": "svc-a", "status": "up"}),
        ("system.health", {"service": "svc-a", "status": "down"}),
    ]


@pytest.mark.asyncio
async def test_connection_error_is_treated_as_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    redis_client = FakeRedis()
    poller = _poller(_settings(), handler, redis_client)

    await poller._check_one("svc-a")

    assert redis_client.published == [("system.health", {"service": "svc-a", "status": "down"})]


@pytest.mark.asyncio
async def test_snapshot_reflects_last_known_status_per_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200) if "svc-a" in str(request.url) else httpx.Response(503)

    poller = _poller(_settings(), handler)

    assert poller.snapshot() == {}  # nothing probed yet
    await poller._check_one("svc-a")
    await poller._check_one("svc-b")

    assert poller.snapshot() == {"svc-a": "up", "svc-b": "down"}


@pytest.mark.asyncio
async def test_snapshot_returns_a_copy_not_the_live_dict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    poller = _poller(_settings(), handler)
    await poller._check_one("svc-a")

    snapshot = poller.snapshot()
    snapshot["svc-a"] = "tampered"

    assert poller.snapshot() == {"svc-a": "up"}


class HangingRedis:
    """Simulates a Redis publish that never returns -- reproduces the real
    bug (no client-level socket timeout on the shared Redis connection, see
    `config.py`'s `health_check_overall_timeout_seconds` docstring) where a
    single stuck publish froze the whole poller loop forever after a
    `--force-recreate`, silently serving one stale snapshot indefinitely."""

    async def publish(self, channel: str, data: str) -> None:
        await asyncio.sleep(3600)


@pytest.mark.asyncio
async def test_a_hanging_publish_times_out_instead_of_blocking_forever() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    settings = _settings(health_check_overall_timeout_seconds=0.05)
    poller = _poller(settings, handler, HangingRedis())

    await asyncio.wait_for(poller._check_one("svc-a"), timeout=1.0)  # must not hang the test itself

    # `_check_one_inner` writes `_last_status` before the publish that then
    # hangs, so the status itself is still correctly recorded even though
    # the timeout cut the publish off -- only the pub/sub notification is
    # lost, an acceptable tradeoff for "the loop must never freeze".
    assert poller.snapshot() == {"svc-a": "up"}


@pytest.mark.asyncio
async def test_run_loop_survives_one_service_hanging_forever() -> None:
    """The actual regression: one stuck service must not stop the others
    from being checked, and must not stop the loop from reaching its next
    cycle at all."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    class SelectivelyHangingRedis:
        async def publish(self, channel: str, data: str) -> None:
            if "svc-hangs" in data:
                await asyncio.sleep(3600)

    settings = _settings(
        monitored_services=["svc-ok", "svc-hangs"],
        health_check_overall_timeout_seconds=0.05,
        health_poll_interval_seconds=0,
    )
    poller = _poller(settings, handler, SelectivelyHangingRedis())

    # One full `_run` iteration's worth of work, bounded so a real freeze
    # fails the test instead of hanging the suite.
    async def one_cycle() -> None:
        results = await asyncio.gather(
            *(poller._check_one(name) for name in settings.monitored_services),
            return_exceptions=True,
        )
        assert not any(isinstance(r, Exception) for r in results)

    await asyncio.wait_for(one_cycle(), timeout=1.0)

    assert poller.snapshot() == {"svc-ok": "up", "svc-hangs": "up"}
