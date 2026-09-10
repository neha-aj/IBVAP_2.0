# IBVAP — Implementation Guide (IG)

**Purpose:** The reference every future build session follows. Later prompts should say "per the Implementation Guide, build Milestone X" rather than re-deriving conventions.

---

## 1. Build Order & Milestones

Each milestone ends with a **fully working, demoable, testable** system — never a half-wired one.

| # | Milestone | Delivers | Frontend page(s) unlocked | Completion criteria |
|---|---|---|---|---|
| M0 | Platform scaffolding | `docker-compose.yml`, shared service template (FastAPI app factory, logging, `/health`, `/ready`, config via `pydantic-settings`), Postgres + Redis containers, NGINX skeleton routing | none yet | `docker compose up` brings up empty-but-healthy stack; `/health` green on every service |
| M1 | Auth Service | Users table, login/refresh/logout, JWT issuance, RBAC middleware library reused by all services | (enables auth on everything after) | Can log in via API, receive/validate JWT, RBAC denies wrong-role calls; unit + contract tests pass |
| M2 | Camera Management Service | Camera CRUD, sector/zone tables, camera status field, Settings-page-shaped config endpoints | Cameras, Settings (static parts), Dashboard camera counts | `GET/POST/PUT/DELETE /cameras` fully functional against Postgres; frontend `cameraService` swapped from mock and Cameras page renders real DB rows |
| M3 | Stream Ingestion Service | Per-camera RTSP/USB capture, live preview (MJPEG/HLS), heartbeat → camera status transitions | Surveillance page shows a real "LIVE" feed instead of placeholder; camera status dots reflect reality | A test camera (file-looped RTSP) streams end-to-end to a browser; disconnecting it flips status to `offline` within the heartbeat timeout |
| M4 | Detection Service | YOLO inference on ingested frames, normalized bbox output, current-detections cache | Surveillance page bounding-box overlay is real | Overlay boxes on the test camera match ground-truth objects in the test video within acceptable IoU; `GET /cameras/{id}/detections/current` returns live data |
| M5 | Tracking Service | ByteTrack integration, persistent `track_id`s | `trackId` in overlay is stable across frames | Track IDs remain stable across a continuous test clip with occlusion; track lifecycle events observable on the stream |
| M6 | Event/Alert Service | Rule engine (thresholds, offline-alert, basic zone rule), Events/Alerts REST, Redis Pub/Sub emit | Events, Alerts pages fully real; Dashboard "Active Alerts"/"Events Today" real | Triggering a rule in the test scenario produces a row visible via `GET /events` and `GET /alerts` within one polling interval |
| M7 | Media Storage Service | Snapshot capture + storage + retrieval | `EventDetails` image placeholder can be filled with a real snapshot URL | Alert/event creation always has a resolvable `snapshotUrl`; snapshot survives service restart (persisted volume) |
| M8 | Realtime Gateway | WebSocket endpoint, topic subscription, auth on connect | All pages update live without refresh | Browser WS client receives `alert.new`/`event.new`/`camera.status_changed`/`detection.new` within the pipeline's expected latency budget |
| M9 | Analytics Service | Aggregation jobs/materialized views, Dashboard stat aggregate + Analytics page endpoints | Dashboard, Analytics fully real | All four Analytics charts and all six Dashboard stat cards backed by live aggregates, verified against manually-computed expected values on test data |
| M10 | Hardening & Ops | Prometheus/Grafana, structured logging correlation IDs, load test, CI pipeline, security pass (rate limiting, secrets audit) | — | Load test report meets §11 scaling targets; CI runs full test suite green on every PR |

No milestone begins before the previous one's completion criteria are met and demonstrated against the running stack (not just unit tests in isolation).

## 2. Module Dependencies

```
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7
                                  ↘        ↘
                                   M8 (needs M6 events) 
                                              M9 (needs M2,M4,M6 data to aggregate)
                                                        M10 (needs everything)
```
M8 can start in parallel with M7 once M6 is done (both only need the Redis Pub/Sub contract from M6).

## 3. Coding Standards

- **Python 3.12**, type hints mandatory on every function signature (`mypy --strict` in CI).
- **Formatting/linting**: `black`, `ruff`, `isort` — enforced via pre-commit hooks and CI gate.
- **Async-first**: all I/O-bound endpoints/handlers are `async def`; CPU-bound inference runs in a worker/process pool (never blocking the event loop).
- **Repository pattern**: every service has a `repositories/` layer wrapping SQLAlchemy; route handlers never construct raw queries — they call a repository method. This is what makes each service's persistence swappable/testable in isolation.
- **Dependency Injection**: FastAPI `Depends()` for DB sessions, current-user, repositories, and settings — no global mutable state, no service-locator anti-pattern.
- **Pydantic v2** models: strict separation of `*Create` / `*Update` / `*Read` schemas from ORM models; ORM models never returned directly from an endpoint.
- **Docstrings**: Google-style, required on every public function/class.
- **No service imports another service's package.** Shared code (JWT validation, logging setup, base settings) lives in a small internal shared library (`ibvap_common`) published to an internal package index or vendored — never imported as `../other-service/...`.

## 4. Naming Conventions

- **Services**: `kebab-case` folder/container names, e.g. `camera-service`, `event-alert-service`.
- **Python packages/modules**: `snake_case`.
- **Database tables**: `snake_case`, plural (`cameras`, `alerts`, `detections`).
- **Database columns**: `snake_case`; foreign keys `{singular_table}_id` (e.g. `camera_id`).
- **API JSON fields**: `camelCase` at the HTTP boundary (Pydantic `alias_generator=to_camel`) to match the frontend's existing mock shapes exactly (`cameraName`, `trackId`, `lastActive`, etc.) — internal Python stays `snake_case`.
- **Redis keys/streams**: `{domain}:{id}:{purpose}`, e.g. `cam:BOP-01-CAM-01:frames`.
- **Enum values**: lower-case strings matching the frontend's `Badge`/`StatusDot` tone vocabulary exactly: camera status `online|warning|offline`; severity `critical|high|medium|low`; alert/event status `active|reviewing|resolved`.

## 5. API Conventions

- Base path `/api/v1/...`; version bump only on breaking change.
- Resource-oriented, plural nouns, standard verbs (`GET/POST/PUT/PATCH/DELETE`).
- Pagination: `?page=&pageSize=` with `{items, total, page, pageSize}` envelope on list endpoints.
- Filtering via query params named after the frontend's filter UI (`status`, `detection`, `camera`, `severity`, `date`, `search`) — see API Specification for the full per-endpoint list.
- Errors: RFC 7807-style problem JSON `{type, title, status, detail, traceId}`.
- All timestamps ISO-8601 UTC; frontend formats locally (`formatDate`/`formatTime` utils already exist client-side).
- WebSocket messages: `{"event": "alert.new", "data": {...}}` envelope; client subscribes via `{"action":"subscribe","topics":["alerts","camera:BOP-01-CAM-01"]}`.

## 6. Database Conventions

- One Alembic migration head per schema/service; migrations are the only way schema changes ship — no manual DDL against running environments.
- Every table: `id` (UUID PK), `created_at`, `updated_at` (server-side defaults/triggers).
- Foreign keys always indexed; timestamp columns used in filters (e.g. `events.created_at`) always indexed; composite index on `(camera_id, created_at)` for per-camera time-range queries.
- No cross-schema foreign keys (services own their data); cross-service references stored as plain UUID columns, resolved via API calls or denormalized fields when the frontend contract requires it (see Frontend Analysis §5).

## 7. Folder Conventions (per service)

```
service-name/
  app/
    main.py                 # FastAPI app factory, router include
    api/                     # route modules (thin, call services/repositories)
    schemas/                 # Pydantic request/response models
    models/                  # SQLAlchemy ORM models
    repositories/             # data-access layer
    services/                 # business logic
    core/                     # config, security, logging setup
    ws/                       # (only realtime-gateway) connection manager
  alembic/
    versions/
  tests/
    unit/
    integration/
  Dockerfile
  pyproject.toml
  README.md
```

## 8. Git Workflow

- Trunk-based development: `main` always deployable.
- Feature branches: `feature/{milestone}-{short-desc}` (e.g. `feature/m4-detection-service`), squash-merged via PR.
- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`) — enables changelog generation.
- Every PR must: pass CI (lint, type-check, unit + integration tests), reference the milestone, include/updated tests for changed behavior.
- Tag a release (`v0.{milestone}.0`) at the end of each milestone once demo criteria are confirmed.

## 9. Testing Strategy (build-time detail)

- **Unit**: repository methods (against a test DB via `testcontainers-postgres` or a transactional-rollback fixture), business/rule-engine logic (pure functions where possible), Pydantic schema round-trips.
- **Contract**: OpenAPI schema generated per service checked against the API Specification document in CI (fails the build on drift).
- **Integration**: `docker-compose.test.yml` spins the full stack + a synthetic camera source; a test suite drives the pipeline end-to-end and asserts on REST/WebSocket outputs.
- **Coverage gate**: ≥80% line coverage per service enforced in CI (business logic and repositories; excludes generated migration files).

## 10. Definition of Done (applies to every milestone)

1. All endpoints/events for that milestone implemented per the API Specification.
2. Migrations applied cleanly on a fresh database.
3. Unit + integration tests green in CI.
4. `docker compose up` demonstrates the milestone's "unlocked" frontend page(s) working against real data (manual or scripted demo).
5. Document any deviation from the SAS/API Spec in that milestone's PR description — the source-of-truth documents are updated in the same PR, never left stale.

## 11. Roadmap Beyond Phase 1 (reference only — not built yet)

Phase 2: Re-ID (person/vehicle), ANPR, richer intrusion/loitering zone editor UI, fire/smoke detection, tamper detection, animal detection, cross-camera analytics. Each ships as a new service per SAS §14, following this same Implementation Guide unchanged — new milestones simply append to the table in §1.
