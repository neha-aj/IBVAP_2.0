"""Tracks connected WebSocket clients and their subscribed topics, and
fans out one Pub/Sub message to every connection currently subscribed to
its topic (SAS §69: "subscribes to Redis Pub/Sub channels and fans out to
connected clients, per-connection auth + topic subscription")."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import WebSocket

from ibvap_common.logging import get_logger

from app.ws.topics import is_valid_topic

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, set[str]] = {}

    def connect(self, websocket: WebSocket) -> str:
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = websocket
        self._subscriptions[connection_id] = set()
        return connection_id

    def disconnect(self, connection_id: str) -> None:
        self._connections.pop(connection_id, None)
        self._subscriptions.pop(connection_id, None)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def subscribe(self, connection_id: str, topics: list[str]) -> None:
        valid = {t for t in topics if is_valid_topic(t)}
        self._subscriptions.setdefault(connection_id, set()).update(valid)

    def unsubscribe(self, connection_id: str, topics: list[str]) -> None:
        self._subscriptions.get(connection_id, set()).difference_update(topics)

    def subscriptions_for(self, connection_id: str) -> set[str]:
        return set(self._subscriptions.get(connection_id, set()))

    async def broadcast(self, topic: str, message: dict[str, Any]) -> None:
        stale: list[str] = []
        for connection_id, topics in list(self._subscriptions.items()):
            if topic not in topics:
                continue
            websocket = self._connections.get(connection_id)
            if websocket is None:
                continue
            try:
                await websocket.send_json(message)
            except Exception as exc:  # noqa: BLE001
                logger.info("ws_send_failed", connection_id=connection_id, error=str(exc))
                stale.append(connection_id)

        for connection_id in stale:
            self.disconnect(connection_id)
