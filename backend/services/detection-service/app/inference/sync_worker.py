"""M11 §7: drains `EdgeOutbox` to the central Redis instance in batches,
with exponential backoff on connection failure -- detections queue locally
and nothing is lost during an outage; nothing here blocks local alerting
(local_rules.py runs independently against the same outbox).
"""

from __future__ import annotations

import asyncio
import json

from ibvap_common.logging import get_logger

from app.inference.edge_outbox import EdgeOutbox
from app.schemas.detection import Detection
from app.streaming.detection_publisher import DetectionPublisher

logger = get_logger(__name__)


class SyncWorker:
    def __init__(
        self,
        *,
        outbox: EdgeOutbox,
        publisher: DetectionPublisher,
        batch_size: int,
        interval_seconds: float,
        initial_backoff_seconds: float,
        max_backoff_seconds: float,
    ) -> None:
        self._outbox = outbox
        self._publisher = publisher
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._initial_backoff_seconds = initial_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._backoff_seconds = initial_backoff_seconds
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name="edge-sync-worker")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stop_requested:
            try:
                await self.sync_once()
                self._backoff_seconds = self._initial_backoff_seconds  # reset once the link is clearly good again
                await asyncio.sleep(self._interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("edge_sync_failed", error=str(exc), backoff_seconds=round(self._backoff_seconds, 1))
                await asyncio.sleep(self._backoff_seconds)
                self._backoff_seconds = min(self._backoff_seconds * 2, self._max_backoff_seconds)

    async def sync_once(self) -> int:
        """Drains up to one batch, publishing each row to central Redis and
        marking it synced immediately after its own successful publish
        (not batched at the end) -- if a later row in the batch fails, at
        most that one row risks being re-published on the next attempt,
        not the whole batch (SAS §11's own at-least-once processing
        precedent, same tradeoff `FrameConsumer`'s ack-even-on-failure
        already makes). Returns how many rows were synced; raises on a
        connection failure so `_run`'s backoff kicks in."""
        batch = await self._outbox.dequeue_batch(self._batch_size)
        synced = 0
        for row in batch:
            detections = [Detection(**d) for d in json.loads(row["detections_json"])]
            await self._publisher.publish(row["camera_id"], detections, loop_generation=row["loop_generation"])
            await self._outbox.mark_synced([row["id"]])
            synced += 1
        return synced
