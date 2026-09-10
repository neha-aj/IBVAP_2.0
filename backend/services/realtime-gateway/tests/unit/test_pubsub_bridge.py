import json

import pytest

from app.core.config import Settings
from app.streaming.pubsub_bridge import PubSubBridge


def _settings() -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s")


class FakeConnectionManager:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[str, dict]] = []

    async def broadcast(self, topic: str, message: dict) -> None:
        self.broadcasts.append((topic, message))


def _bridge(manager: FakeConnectionManager) -> PubSubBridge:
    return PubSubBridge(redis_client=None, connection_manager=manager, settings=_settings())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_event_new_routes_to_events_topic() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"event.new", json.dumps({"id": "1"}).encode())

    assert manager.broadcasts == [("events", {"event": "event.new", "data": {"id": "1"}})]


@pytest.mark.asyncio
async def test_alert_new_and_updated_route_to_alerts_topic() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"alert.new", json.dumps({"id": "1"}).encode())
    await bridge._dispatch(b"alert.updated", json.dumps({"id": "1"}).encode())

    assert [topic for topic, _ in manager.broadcasts] == ["alerts", "alerts"]


@pytest.mark.asyncio
async def test_system_health_routes_to_system_topic() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"system.health", json.dumps({"service": "camera-service", "status": "down"}).encode())

    assert manager.broadcasts == [
        ("system", {"event": "system.health", "data": {"service": "camera-service", "status": "down"}})
    ]


@pytest.mark.asyncio
async def test_camera_status_changed_routes_to_that_cameras_topic() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"camera.status_changed", json.dumps({"cameraId": "FILE-01", "status": "offline"}).encode())

    assert manager.broadcasts == [
        ("camera:FILE-01", {"event": "camera.status_changed", "data": {"cameraId": "FILE-01", "status": "offline"}})
    ]


@pytest.mark.asyncio
async def test_detection_new_routes_to_that_cameras_topic() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"detection.new", json.dumps({"cameraId": "FILE-02", "detections": []}).encode())

    assert manager.broadcasts[0][0] == "camera:FILE-02"


@pytest.mark.asyncio
async def test_per_camera_message_missing_camera_id_is_dropped_not_broadcast() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"camera.status_changed", json.dumps({"status": "offline"}).encode())

    assert manager.broadcasts == []


@pytest.mark.asyncio
async def test_malformed_json_is_dropped_not_raised() -> None:
    manager = FakeConnectionManager()
    bridge = _bridge(manager)

    await bridge._dispatch(b"event.new", b"not-json")

    assert manager.broadcasts == []
