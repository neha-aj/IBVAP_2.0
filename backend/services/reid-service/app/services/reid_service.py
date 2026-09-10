"""Orchestrates Re-ID (doc09 §2.2 Person, §2.3 Vehicle -- "identical
architecture...filtered to object_type=vehicle"): on a new track, fetch the
current frame -> crop -> embed -> persist (one embedding per track, taken
at first sighting -- see docstring on `process_track_event` for why this
simplifies doc09's "best-confidence frame from the track's lifetime"). On
search, resolve a query embedding (from an existing track or an uploaded
image) and rank the embedding index by cosine similarity.

One `ReidService` instance handles exactly one `object_type` ("person" or
"vehicle") -- `object_type`/`embedding_factory`/`crop_min_size` parameterize
that, rather than two near-duplicate classes, since the orchestration logic
itself (crop/embed/persist/search) doesn't otherwise differ (Phase 2 M17
reuses this for vehicles). `embed` is an injected callable (not hardcoded
to `ImageEmbedder.embed`) so this orchestration logic is unit-testable
without the real ResNet-50 model loaded -- main.py wires the real
implementation at startup.
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from ibvap_common.logging import get_logger
from ibvap_common.stream_auth import build_resource_url

from app.core.config import Settings
from app.inference import preprocessing
from app.models.person_embedding import PersonEmbedding
from app.repositories.embedding_repo import EmbeddingRepository
from app.schemas.internal import TrackEvent
from app.schemas.reid import MatchResult
from app.streaming.camera_client import CameraClient
from app.streaming.media_client import MediaClient

logger = get_logger(__name__)

EmbedFn = Callable[[np.ndarray], list[float]]


class ReidService:
    def __init__(
        self,
        *,
        settings: Settings,
        embedding_repo: EmbeddingRepository,
        camera_client: CameraClient,
        media_client: MediaClient,
        embed: EmbedFn,
        object_type: str = "person",
        embedding_factory: Callable[..., object] = PersonEmbedding,
        crop_min_size: int | None = None,
    ) -> None:
        self._settings = settings
        self._embedding_repo = embedding_repo
        self._camera_client = camera_client
        self._media_client = media_client
        self._embed = embed
        self._object_type = object_type
        self._embedding_factory = embedding_factory
        # Falls back to the person setting when a caller doesn't pass one --
        # keeps every existing call site (tests included) working unchanged.
        self._crop_min_size = crop_min_size if crop_min_size is not None else settings.person_crop_min_size_px

    async def process_track_event(self, event: TrackEvent):
        """One embedding per track, taken at the *first* sighting we can act
        on -- doc09 §2.2 describes picking the track's single best-confidence
        frame, but `cam:{id}:tracks` (what this service actually consumes)
        carries no confidence value at all (only the detections stream
        does, and only detection-service's own consumer sees that), so
        "best" isn't a signal available here. Simplified to "first frame we
        have," a documented deviation, not a silent shortcut."""
        if event.object_type != self._object_type or event.bbox is None:
            return None
        if event.event not in ("track.started", "track.updated"):
            return None

        existing = await self._embedding_repo.get_latest_by_track(camera_id=event.camera_id, track_id=event.track_id)
        if existing is not None:
            return None  # already embedded this track -- doc09's "one embedding per track"

        frame_bytes = await self._camera_client.get_current_frame(event.camera_id)
        if frame_bytes is None:
            return None
        frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None

        crop = preprocessing.crop_bbox_percent(
            frame, x=event.bbox.x, y=event.bbox.y, width=event.bbox.width, height=event.bbox.height,
        )
        if crop.size == 0 or min(crop.shape[:2]) < self._crop_min_size:
            return None

        vector = self._embed(crop)

        snapshot_id = None
        encoded_ok, encoded = cv2.imencode(".jpg", crop)
        if encoded_ok:
            stored = await self._media_client.store_person_crop(
                camera_id=event.camera_id, jpeg_bytes=encoded.tobytes()
            )
            if stored is not None:
                snapshot_id = stored.id

        embedding_row = await self._embedding_repo.create(
            self._embedding_factory(
                track_id=event.track_id, camera_id=event.camera_id, embedding=vector, snapshot_id=snapshot_id,
            )
        )
        logger.info(f"{self._object_type}_embedding_created", camera_id=event.camera_id, track_id=event.track_id)
        return embedding_row

    async def has_embedding(self, *, camera_id: str, track_id: str) -> bool:
        return await self._embedding_repo.get_latest_by_track(camera_id=camera_id, track_id=track_id) is not None

    async def search_by_track(self, *, camera_id: str, track_id: str) -> list[MatchResult]:
        query_row = await self._embedding_repo.get_latest_by_track(camera_id=camera_id, track_id=track_id)
        if query_row is None:
            return []
        return await self._search(query_row.embedding, exclude_track_id=track_id)

    async def search_by_image(self, jpeg_bytes: bytes) -> list[MatchResult]:
        frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return []
        vector = self._embed(frame)
        return await self._search(vector, exclude_track_id=None)

    async def _search(self, query_embedding: list[float], *, exclude_track_id: str | None) -> list[MatchResult]:
        rows = await self._embedding_repo.search_similar(
            query_embedding, exclude_track_id=exclude_track_id, limit=self._settings.max_search_results,
        )
        matches: list[MatchResult] = []
        for row, similarity in rows:
            if similarity < self._settings.similarity_threshold:
                continue
            camera_info = await self._camera_client.get_camera_info(row.camera_id)
            snapshot_id = str(row.snapshot_id) if row.snapshot_id else None
            matches.append(
                MatchResult(
                    track_id=row.track_id,
                    camera_id=row.camera_id,
                    camera_name=camera_info.name if camera_info else row.camera_id,
                    timestamp=row.created_at,
                    similarity_score=round(similarity, 4),
                    snapshot_id=snapshot_id,
                    snapshot_url=build_resource_url(
                        path=f"/media/snapshots/{snapshot_id}", resource=snapshot_id, settings=self._settings
                    )
                    if snapshot_id
                    else None,
                )
            )
        return matches
