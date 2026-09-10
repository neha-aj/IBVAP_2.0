import pytest

from app.ws.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self._fail = fail

    async def send_json(self, message: dict) -> None:
        if self._fail:
            raise RuntimeError("connection closed")
        self.sent.append(message)


def test_connect_assigns_an_id_and_starts_with_no_subscriptions() -> None:
    manager = ConnectionManager()
    connection_id = manager.connect(FakeWebSocket())
    assert manager.subscriptions_for(connection_id) == set()
    assert manager.connection_count == 1


@pytest.mark.asyncio
async def test_broadcast_only_reaches_subscribed_connections() -> None:
    manager = ConnectionManager()
    ws_subscribed = FakeWebSocket()
    ws_unsubscribed = FakeWebSocket()
    subscribed_id = manager.connect(ws_subscribed)
    manager.connect(ws_unsubscribed)
    manager.subscribe(subscribed_id, ["alerts"])

    await manager.broadcast("alerts", {"event": "alert.new", "data": {}})

    assert len(ws_subscribed.sent) == 1
    assert ws_unsubscribed.sent == []


@pytest.mark.asyncio
async def test_broadcast_ignores_invalid_topics_never_subscribed() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = manager.connect(ws)
    manager.subscribe(connection_id, ["not-a-real-topic"])

    await manager.broadcast("alerts", {"event": "alert.new", "data": {}})

    assert ws.sent == []


def test_unsubscribe_removes_only_the_given_topics() -> None:
    manager = ConnectionManager()
    connection_id = manager.connect(FakeWebSocket())
    manager.subscribe(connection_id, ["alerts", "events"])

    manager.unsubscribe(connection_id, ["alerts"])

    assert manager.subscriptions_for(connection_id) == {"events"}


@pytest.mark.asyncio
async def test_broadcast_disconnects_stale_connections_on_send_failure() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket(fail=True)
    connection_id = manager.connect(ws)
    manager.subscribe(connection_id, ["alerts"])

    await manager.broadcast("alerts", {"event": "alert.new", "data": {}})

    assert manager.connection_count == 0


def test_disconnect_is_safe_to_call_twice() -> None:
    manager = ConnectionManager()
    connection_id = manager.connect(FakeWebSocket())
    manager.disconnect(connection_id)
    manager.disconnect(connection_id)  # must not raise
    assert manager.connection_count == 0
