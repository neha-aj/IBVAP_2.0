-- Runs once, on first Postgres container initialization (empty data volume).
-- Pre-creates one schema per microservice per DB Spec §1-§5. Each service's
-- own Alembic migrations then create tables inside its schema only.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- Phase 2 M16 (Person/Vehicle Re-ID) embedding similarity search -- needs
-- the pgvector/pgvector Postgres image (see docker-compose.yml's postgres
-- service comment), not a vanilla postgres image.
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS camera;
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS media;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS anpr;
CREATE SCHEMA IF NOT EXISTS reid;
