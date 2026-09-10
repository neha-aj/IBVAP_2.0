"""M11 §7 edge deployment profile: a local, durable queue for detections
when `Settings.deployment_mode == "edge"`, so a site with an intermittent
link to the central Redis instance never loses a detection -- it queues
locally (this file) and syncs once connectivity returns (`sync_worker.py`).

Plain stdlib `sqlite3` in WAL mode -- not a new dependency, and run off the
event loop via `asyncio.to_thread` the same way this project already
handles every other blocking native call (e.g. `CameraWorker`'s OpenCV
reads).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path


class EdgeOutbox:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY,
                    camera_id TEXT NOT NULL,
                    detections_json TEXT NOT NULL,
                    loop_generation INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    synced_at REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_outbox_unsynced ON outbox (created_at) WHERE synced_at IS NULL"
            )
            # M11 §7 EDGE_LOCAL_RULES: alerts a LocalRuleEngine fires while
            # disconnected, kept in the same outbox file for simplicity.
            # Syncing these to event-alert-service's central alerts table
            # (deduplicated by `idempotency_key`) is the one integration
            # step not built here -- see local_rules.py's module docstring
            # for why that's out of this PR's authorized file scope.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_alerts (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    synced_at REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    # --- detections ---

    async def enqueue(self, *, camera_id: str, detections_json: str, loop_generation: int = 0) -> str:
        entry_id = str(uuid.uuid4())
        await asyncio.to_thread(self._enqueue_sync, entry_id, camera_id, detections_json, loop_generation)
        return entry_id

    def _enqueue_sync(self, entry_id: str, camera_id: str, detections_json: str, loop_generation: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO outbox (id, camera_id, detections_json, loop_generation, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry_id, camera_id, detections_json, loop_generation, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    async def dequeue_batch(self, limit: int) -> list[dict]:
        return await asyncio.to_thread(self._dequeue_batch_sync, limit)

    def _dequeue_batch_sync(self, limit: int) -> list[dict]:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, camera_id, detections_json, loop_generation FROM outbox "
                "WHERE synced_at IS NULL ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    async def mark_synced(self, ids: list[str]) -> None:
        if not ids:
            return
        await asyncio.to_thread(self._mark_synced_sync, ids)

    def _mark_synced_sync(self, ids: list[str]) -> None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"UPDATE outbox SET synced_at = ? WHERE id IN ({placeholders})", (time.time(), *ids))
            conn.commit()
        finally:
            conn.close()

    async def count_pending(self) -> int:
        return await asyncio.to_thread(self._count_sync, "outbox", synced=False)

    async def count_synced(self) -> int:
        return await asyncio.to_thread(self._count_sync, "outbox", synced=True)

    def _count_sync(self, table: str, *, synced: bool) -> int:
        conn = self._connect()
        try:
            clause = "IS NOT NULL" if synced else "IS NULL"
            return conn.execute(f"SELECT count(*) FROM {table} WHERE synced_at {clause}").fetchone()[0]  # noqa: S608
        finally:
            conn.close()

    # --- local alerts (EDGE_LOCAL_RULES) ---

    async def record_local_alert(
        self, *, idempotency_key: str, camera_id: str, event_type: str, description: str, severity: str
    ) -> bool:
        """Returns False (no-op) if this exact idempotency_key was already
        recorded -- a rule re-firing on overlapping detection batches must
        not create duplicate local alerts."""
        return await asyncio.to_thread(
            self._record_local_alert_sync, idempotency_key, camera_id, event_type, description, severity
        )

    def _record_local_alert_sync(
        self, idempotency_key: str, camera_id: str, event_type: str, description: str, severity: str
    ) -> bool:
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT 1 FROM local_alerts WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return False
            conn.execute(
                "INSERT INTO local_alerts "
                "(id, idempotency_key, camera_id, event_type, description, severity, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), idempotency_key, camera_id, event_type, description, severity, time.time()),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    async def count_pending_local_alerts(self) -> int:
        return await asyncio.to_thread(self._count_sync, "local_alerts", synced=False)


class EdgeOutboxPublisher:
    """Duck-typed as a `DetectionPublisher` -- same `.publish(camera_id,
    detections, loop_generation=...)` shape `FrameConsumer`/`ModalityFeed`
    already call unconditionally -- so selecting this instead of the real
    `DetectionPublisher` when `deployment_mode == "edge"` is a one-line
    swap of which publisher gets constructed at startup, not a new code
    path through consumer_manager.py or frame_consumer.py."""

    def __init__(self, outbox: EdgeOutbox) -> None:
        self._outbox = outbox

    async def publish(self, camera_id: str, detections: list, *, loop_generation: int = 0) -> None:
        payload = json.dumps([d.model_dump(by_alias=True) for d in detections])
        await self._outbox.enqueue(camera_id=camera_id, detections_json=payload, loop_generation=loop_generation)
