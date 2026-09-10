"""Shared by every embedding table (`person_embeddings`, `vehicle_embeddings`)
and their alembic migrations: both use the exact same ResNet-50 backbone
(app/inference/embedder.py) as a general-purpose feature extractor, so both
tables need the identical column width. A plain module-level constant, not
`Settings.embedding_dimension`, deliberately -- this sizes a SQLAlchemy
column type at *import* time, which happens before any settings/env vars
are guaranteed to be configured (e.g. a bare `pytest` run, or alembic's own
model registration import)."""

EMBEDDING_DIMENSION = 2048
