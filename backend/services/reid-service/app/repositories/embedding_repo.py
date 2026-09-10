from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_dimension import EMBEDDING_DIMENSION


class EmbeddingRepository:
    """Generic over which embedding table it reads/writes -- `model` is
    `PersonEmbedding` or `VehicleEmbedding` (Phase 2 M17), both column-for-
    column identical (see either model's own docstring for why they're
    still separate tables). One implementation instead of two near-
    duplicate repo classes, since the actual query logic doesn't care which
    table it's pointed at."""

    def __init__(self, session: AsyncSession, model: type) -> None:
        self._session = session
        self._model = model

    async def create(self, embedding_row):
        self._session.add(embedding_row)
        await self._session.commit()
        await self._session.refresh(embedding_row)
        return embedding_row

    async def get_latest_by_track(self, *, camera_id: str, track_id: str):
        result = await self._session.execute(
            select(self._model)
            .where(self._model.camera_id == camera_id, self._model.track_id == track_id)
            .order_by(self._model.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def search_similar(self, query_embedding: list[float], *, exclude_track_id: str | None, limit: int):
        """Returns (row, similarity) pairs, nearest first. pgvector's
        `<=>` operator is cosine *distance*; similarity = 1 - distance
        (doc11 §2's "cosine similarity" threshold is on this same 0-1
        scale, 1.0 = identical)."""
        # Explicit cast is required, not cosmetic: pgvector's SQLAlchemy
        # `Vector` type has no bind_expression, so a bare bound parameter
        # reaches Postgres as an untyped ("unknown") literal. asyncpg's
        # prepared-statement protocol type-checks parameters against the
        # query before execution and can't resolve `vector <=> unknown`,
        # failing with "operator does not exist: vector <=> unknown" --
        # confirmed live the first time /reid/search ran end-to-end. The
        # explicit cast() gives Postgres a concrete type for the parameter
        # up front. (The `vector` type and its `<=>` operator both live in
        # the `public` schema -- reid-service's connection search_path is
        # extended to include `public` in app/db/session.py specifically
        # so both this cast and the operator itself resolve unqualified.)
        distance = self._model.embedding.cosine_distance(cast(query_embedding, Vector(EMBEDDING_DIMENSION)))
        stmt = select(self._model, (1 - distance).label("similarity")).order_by(distance).limit(limit)
        if exclude_track_id is not None:
            stmt = stmt.where(self._model.track_id != exclude_track_id)
        result = await self._session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]
