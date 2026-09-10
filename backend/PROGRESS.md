# IBVAP Progress Reference

Snapshot of working code as of 2026-09-07. This is a reference doc, not a chronological log — it describes what exists and works right now.

## Standing rules
- Lux-frontend pushes go to branch `Neha` on `github.com/MrPooj/Lux.git` — never `main`.
- ibvap backend commits go to `main` on `neha-aj/Lux_claude`.
- Only commit when explicitly told to.
- From M17 onward: build frontend and backend together, not backend-first.
- Commits end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Every milestone is live-verified against the running docker-compose stack (3 demo cameras: `FILE-C5F172A4`/"My Own Video", `FILE-DDBF01CE`/"Video 2", `FILE-36A14369`/"Video 3") before being considered done.

## Shared architectural patterns
- **Internal event contract**: every new AI microservice reports detections via `POST /internal/events` on event-alert-service. That one path creates `events`/`alerts` rows, captures a snapshot, and publishes to the existing WebSocket pipeline — zero frontend changes needed for new alert types.
- **DB-less microservices** (fire-smoke-service, tamper-service): no Postgres schema, no alembic, no SQLAlchemy — Redis Streams consumer + HTTP event reporting only, mirroring detection-service's precedent.
- **Classical CV over ML** where no trained model/dataset exists for this deployment (ANPR, Re-ID, Fire/Smoke, Tamper all documented this reasoning in code comments).
- **pgvector** for Re-ID embedding similarity (`cosine_distance`, explicit `CAST(... AS VECTOR(n))`; `public` added to reid-service's `search_path` since the extension lives in `public` but the service's default schema is `reid`).
- **Injectable-function pattern** throughout (embed/classify/score functions, event clients) for testability.
- **Docker Compose**: `<<: *common-env` YAML anchor for shared env vars, `X-Internal-Token` header for service-to-service auth, health-only nginx routes for internal-event-contract-only services.

## Milestones built

### M16/M17 — `services/reid-service/` (Person + Vehicle Re-ID)
- `app/models/embedding_dimension.py` — shared `EMBEDDING_DIMENSION = 2048`.
- `app/models/person_embedding.py`, `app/models/vehicle_embedding.py` — column-identical tables.
- `app/repositories/embedding_repo.py` — generic `EmbeddingRepository(session, model)`.
- `app/services/reid_service.py` — generic `ReidService(..., object_type="person"|"vehicle", embedding_factory=...)`.
- `app/inference/embedder.py` — `ImageEmbedder`, ResNet-50, shared by both object types.
- `app/streaming/reconcile_manager.py` — one `TrackConsumer` per camera runs both person + vehicle Re-ID via `reid_services: dict[str, ReidService]`.
- `app/api/reid.py` — `/reid/search`, `/reid/search/upload`, `/reid/matches` all take `?objectType=person|vehicle`.
- Tests: 17 total, passing.
- Committed: `f8957ac` (M16), `089ca22` (M17).

### Frontend (Lux-frontend, branch `Neha`)
- `src/pages/LicensePlates.jsx` — ANPR reads + watchlist.
- `src/pages/PersonSearch.jsx` — Person/Vehicle toggle, Track/Photo search toggle.
- `src/components/cameras/CalibrationConfig.jsx` — Speed Estimation calibration.
- `src/components/cameras/VirtualFenceConfig.jsx` — queue zone type, densityThreshold, line direction.
- `src/services/cameraService.js`, `anprService.js`, `reidService.js`.
- `src/components/layout/Sidebar.jsx` — "Investigation" group.
- Committed: `608c9aa`, `98906c1`.

### M19 — `services/fire-smoke-service/` (new, no DB)
- `app/inference/heuristics.py` — `fire_score()` (HSV warm-hue + RGB ordering), `smoke_score()` (low-saturation/low-texture, with texture discriminator + sky-exclusion band added after live false positives on a sandy path and overcast sky).
- `app/services/fire_smoke_service.py` — per-camera-per-event-type cooldown, fires immediately on first detection.
- Config: `fire_min_area_fraction=0.02`, `smoke_min_area_fraction=0.15`, `sample_interval_seconds=0.3`.
- Tests: 14 total, passing. No frontend changes (by design).
- Committed: `82e5ec3`.

### M20 — `services/tamper-service/` (new, no DB)
- `app/inference/tamper_detector.py` — EMA rolling histogram + edge density baseline per camera; classifies `covered`/`defocused`/`redirected`/`None`.
- `app/services/tamper_service.py` — debounce via 5 consecutive flagged frames, baseline freezes while tampered, alerts once per episode.
- Config: `sample_interval_seconds=1.0`, threshold constants for each deviation type.
- Tests: 12 total, passing. No frontend changes.
- Committed: `edddc1a`.

### Infra for M19/M20
`docker-compose.yml`, `nginx/templates/api-gateway.conf.template`, `monitoring/prometheus.yml` — new service entries with `/health/fire-smoke` and `/health/tamper` routes, both scraped by Prometheus. Neither touches Postgres.

## Ad-hoc fixes

### Login "Failed to fetch"
Cause: a stale orphaned `vite` process squatting on port 5173 (backend CORS locked to that exact origin). Fix: killed the stale process — no code changes.

### Cameras going silently offline — stuck-worker watchdog
Root cause: OpenCV/FFmpeg's `VideoCapture.read()` can hang forever (not crash/return None) after many hours of looping a demo file. Because this happens inside a blocking call run via `asyncio.to_thread`, the task's own `is_running`/`task.done()` check stays `True` forever — no way to detect the hang from inside.

Fix (`services/ingestion-service/`):
- `app/core/config.py` — `stuck_worker_timeout_seconds: int = 60`.
- `app/workers/camera_worker.py` — `self._last_frame_at` set at construction, updated on every real frame read; new `seconds_since_last_frame()`.
- `app/workers/worker_manager.py::_reconcile()` — also checks `seconds_since_last_frame() > stuck_worker_timeout_seconds`; a stuck-but-"running" worker is force-stopped and replaced (`camera_worker_stuck_restarting` log vs pre-existing `camera_worker_restarting`).
- Tests: 6 new (2 in `test_camera_worker.py`, 4 in `test_worker_manager.py`); full ingestion-service suite is 14, all passing, none of the pre-existing tests modified.
- This is a second, independent failsafe alongside the pre-existing `heartbeat_timeout_seconds` (which only catches `read()` returning `None` repeatedly, not hanging forever).
- Committed: `43c3666`.

### M21 — Animal Detection + PPE Detection Service
**Animal Detection** (config change, no new service, per doc11 §7):
- `detection-service/app/inference/base.py::COCO_TYPE_MAP` — added COCO animal class ids (cat/dog/horse/sheep/cow/elephant/bear/zebra/giraffe) → `"animal"`.
- `DetectionType`/`ObjectType` Literals widened to include `"animal"` across every service that parses a detection/track event off a shared Redis Stream (detection-service, tracking-service, anpr-service, reid-service, event-alert-service, camera-service) — `cam:{id}:detections`/`cam:{id}:tracks` carry every object type unfiltered, so parsing must accept the value even where a service only ever acts on person/vehicle.
- `tracking-service/app/tracking/bytetrack_runner.py` — `_CLASS_BY_TYPE`/`_TYPE_BY_CLASS` gained `"animal": 2` (ByteTrack's own internal class id, unrelated to COCO's).
- Zone/intrusion rules in event-alert-service already key off bbox position, not object_type — verified no engine change needed for animal tracks to flow through zone-crossing rules identically to person/vehicle.
- Tests: `detection-service/tests/unit/test_detection_publisher.py` (animal-mapping test added, pre-existing "unmapped class" test's fixture id changed since it's now mapped), `tracking-service/tests/unit/test_bytetrack_runner.py` (animal round-trip test added).

**PPE Detection** — new `services/ppe-service/` (DB-less, doc09 §2.8):
- `app/inference/ppe_heuristics.py` — `classify_ppe()`, a classical color-region heuristic for high-vis vest coverage over the crop's torso band (HSV hue/saturation/value thresholds). Deliberately does **not** check for a helmet — doc11 §5's documented fallback is explicitly scoped to "high-vis vests only" when no fine-tuned PPE model exists; no classical equivalent is documented for helmet presence.
- `app/services/ppe_service.py::PPEService` — per-track (camera_id, track_id) state: consumes `cam:{id}:tracks`, checks the track's bbox against zones fetched from camera-service, and only classifies if inside a `requires_ppe` zone. Debounces (`violation_debounce_updates`) before the first medium-severity violation, escalates to a second high-severity violation after sustained non-compliance (`escalation_violation_updates`), resets on compliance/zone-exit/track-lost.
- `app/rules/zone_geometry.py` — point-in-polygon zone check, duplicated from event-alert-service's own (IG §3: no cross-service imports).
- `app/streaming/{camera_client,event_client,track_consumer,reconcile_manager}.py` — one `TrackConsumer` + `PPEService` per camera, same discovery/restart pattern as every other pipeline stage. Reports violations via the shared internal event contract (`POST /internal/events`, `event_type: "PPE Violation"`); missing items go into `description` text (matching every other zone-scoped rule's convention — `ExternalDetectionEvent` has no structured metadata field).
- Tests: `test_ppe_heuristics.py` (7), `test_ppe_service.py` (16) — 23 total, all passing.
- Infra: new docker-compose service, `/health/ppe` nginx route, Prometheus scrape target.

**`camera.zones.requires_ppe` column** (camera-service, alembic `0004`):
- `app/models/zone.py`, `app/schemas/zone.py`, `app/repositories/zone_repo.py`, `app/services/zone_service.py`, `app/api/internal.py` — additive boolean column, default `false`, plumbed through create/update/read exactly like `density_threshold`'s own M14 precedent.
- Tests: 2 new in `test_zone_service.py` (create-defaults-false, update-toggles).

**Analytics compliance panel** (analytics-service, alembic `0004`):
- `analytics.mv_ppe_violations_by_camera` — all-time count of `PPE Violation` events per camera (same all-time convention as `mv_events_by_camera`). Grouped by camera only, not zone — `events.events` has no `zone_id` column (documented scope decision in the migration's own docstring).
- `GET /analytics/ppe-compliance` — new endpoint, `analytics_repo.py::ppe_violations_by_camera()`.

**Frontend (Lux-frontend, branch `Neha`)**:
- `src/components/cameras/VirtualFenceConfig.jsx` — "Requires PPE (hard hat, hi-vis vest)" checkbox on the zone editor, zones only.
- `src/services/analyticsService.js` — `getPpeCompliance()`.
- `src/pages/Analytics.jsx` — "PPE compliance" panel (violations by camera), same list-panel style as "Events by camera".
- No changes needed to Alerts/Events display or `DetectionOverlay` — both already render arbitrary event/object types generically (verified no hardcoded person/vehicle switch exists anywhere in the frontend that would need updating for "animal" or "PPE Violation").

**Live-verified** end-to-end against the running stack: created a real `requires_ppe` zone via the public API, watched `ppe-service` pick it up, crop real frames, classify via the heuristic, and report violations that landed correctly in `events`/`alerts` and the new materialized view/API/UI panel — then deleted the test zone and its generated events/alerts.

Not yet committed (pending explicit go-ahead per standing rule).

### M22 — GPU Model-Serving Consolidation: skipped, documented decision
Evaluated before starting and deliberately **not built**. M22's premise (doc12 §1) is a shared inference layer (Triton or a custom batching server) so multiple GPU-model services share GPU hardware efficiently — justified once several real GPU-capable models exist to consolidate.

**Why it doesn't apply to this deployment right now:**
- Of the "up to five" GPU-model services the roadmap anticipated (ANPR, Re-ID, Face, Fire/Smoke, PPE), only **reid-service** (ResNet-50) actually runs a trained model. ANPR uses a Haar cascade + Tesseract (no GPU model), Fire-Smoke/Tamper/PPE are all classical-CV heuristics (no model, doc09's own documented deviation for each — no trained dataset exists for this deployment), and Face Snapshot (M18) was never built.
- More fundamentally: this deployment's own Docker builds install `torch==2.14.0+cpu` for both `detection-service` and `reid-service` — the CPU-only PyTorch build. There is no GPU in play in the running stack at all right now, so the VRAM/compute-contention problem M22 solves doesn't exist here yet.
- Consolidating a single GPU consumer onto a shared inference server adds a network hop and an extra piece of infrastructure to operate for zero sharing benefit — directly the over-engineering the roadmap's own sequencing note (`14-Phase2-Roadmap.md`'s "Milestone Design Notes") warns M22's placement is meant to avoid.

**Revisit trigger:** real GPU hardware gets provisioned for this deployment, **and** a second real trained-model GPU service exists (e.g. Face Snapshot gets built, or a fine-tuned ANPR/PPE model replaces its current classical-CV fallback). Until both are true, every service keeps loading its own model in-process, same pattern `detection-service` has used since Phase 1 — not a degraded fallback, the same thing that's been running successfully through every milestone including M21's live verification.

### M23 — Deferred Phase 1 Items + Recordings Completion
Investigated each of the three named gaps directly against the running code (the referenced `07-M10-Completion-Summary.md` "M7 notes" don't literally exist in this repo's docs — confirmed the gaps independently from source instead).

**1. `GET /cameras/{id}/snapshot`** (camera-service, public API):
- New endpoint, JWT-protected (`viewer` role) — proxies to Ingestion Service's own internal-only `/internal/cameras/{id}/snapshot` (M2M-token, meant for other services, not a user's browser).
- New `app/clients/ingestion_client.py`.

**2. camera-service upload proxy to Media Service**:
- Confirmed the gap from the code itself: camera-service's own `StorageBackend` interface docstring literally said *"Once M7 lands, camera uploads should be proxied there instead"* — M7 (media-service) has existed the whole time, just never wired.
- New `POST /internal/media/sources` on media-service (M2M-token) — stores the file, returns a **raw filesystem path** (not a URL — Ingestion Service reads `file`-type camera sources straight off disk via `cv2.VideoCapture`, confirmed from `camera_worker.py`'s own comment). `LocalStorageBackend` gained an optional-`url_prefix` raw-path mode for this one case.
- camera-service's upload handler now calls this via new `app/clients/media_client.py`; its own duplicate `LocalStorageBackend`/`StorageBackend` files are deleted, along with its now-unused `media-data` volume mount.

**3. Recording segment producer** (the actual gap: `media.recordings` had zero producer at all — its own model docstring said so directly: *"nothing in the pipeline triggers segment recording yet"*):
- New `POST /media/recordings` on media-service (mirrors `POST /media/snapshots`).
- New `event-alert-service/app/streaming/recording_client.py` — **post-roll only** (Ingestion Service caches just one latest frame per camera, no rolling buffer, so true pre-roll isn't possible without new buffering infrastructure — a documented, deliberate scope reduction from the full pre/post-roll SAS concept). Polls the snapshot endpoint `recording_post_roll_frame_count` times, encodes via `cv2.VideoWriter`, uploads the clip.
- Fires only for `severity == "critical"`, as a **tracked background `asyncio.Task`** (not awaited inline like snapshot capture) — a multi-second capture must never delay the event/alert's own persistence or WS push. `PubSubPublisher` gained a `session_factory` (fresh DB session per background completion, same precedent as reid-service's own session-per-unit-of-work) and a `_background_tasks` set to prevent the task being garbage-collected mid-flight.
- New `recording_id`/`recording_url` columns on **both** `events.events` and `events.alerts` (denormalized onto Alert too, not just Event — `AlertDetails` is this project's actually-wired detail view; `EventDetails.jsx` is an unfinished placeholder component nothing ever renders).
- Tests: `tests/unit/test_recording_client.py` (4, using `httpx.MockTransport` — a legitimate no-real-DB way to test this genuinely more complex client, unlike the established "clients aren't directly unit-tested" precedent elsewhere in this project). `PubSubPublisher.persist_and_publish` itself stays untested at the unit level, matching this service's existing boundary (no test in this project exercises it against a real/fake DB session — verified live instead).

**Frontend (Lux-frontend, branch `Neha`)**:
- `src/pages/Alerts.jsx` — `AlertDetails` renders an inline `<video controls>` for critical alerts once `recordingUrl` lands (shows "Capturing clip..." until then); added a small effect keeping `selectedAlert` synced to the live-updating `alerts` list so an already-open detail panel picks up the recording without needing reselection.
- No changes to Events page — its detail view was never wired up before this milestone either; out of scope to build now.
- No frontend wiring for the new snapshot endpoint — it's JWT-protected (not under the unauthenticated `/media/`or `/stream/` nginx routes the way snapshots/recordings/MJPEG are), so a plain `<img src>` can't use it without a fetch+object-URL wrapper; left as a backend capability for now.

**Live-verified** end-to-end against the running stack: fetched a real snapshot JPEG through the public gateway; uploaded a real video through a throwaway test camera and confirmed it landed via media-service (not camera-service) on the shared volume; fired a real critical-severity event and watched a real MP4 clip get captured, uploaded, attached to both the event and alert rows, served correctly by nginx, and rendered as a playable video in the Alerts UI — then cleaned up all test data (camera, event, alert, recording row, and files).

## Post-M23 ad-hoc fixes (not milestone-numbered)
- **Dashboard 0/0 people/vehicles bug** — fixed, live-verified.
- **Camera WARNING flicker** — diagnosed as CPU contention; user increased Docker's CPU allocation, chose to leave the remainder as-is.
- **Track ID visibility** — Surveillance UI now shows track IDs so the existing "Search by Track" feature is actually usable.
- **Camera config modal close buttons** (DetectionConfig/VirtualFenceConfig/CalibrationConfig) — all three had no way to close them on a short viewport (`fixed inset-0` panel with no internal scroll pushed the header/footer off-screen); fixed with `flex flex-col max-h-[90vh]` + `overflow-y-auto` body.
- **ANPR plate-detection accuracy** — Haar cascade was missing most non-Russian plates with no fallback; added a classical edge-density localizer fallback (`edge_plate_detector.py`) plus a per-(camera, plate text) cooldown (detection stream carries no usable track_id). Live-verified: 2 new distinct reads in ~15 min post-fix vs. 2 total before.
- **Alert-volume/direction-readability fixes** — `alert_min_severity` config (default "medium") gates which `requires_review` firings actually become Alerts, so low-severity Zone Entry/Exit stays Events-only; "Direction Observed" throttle raised 1s→5s per track; compass code translated to a plain-language `description` ("moving toward the bottom of the frame") shown in the Events table.
- **Events CSV export + BI-style Analytics dashboard** — Events page gets an "Export to Excel" (CSV) button; Analytics page gets KPI cards, a new Movement Direction Flow chart (wired to an existing-but-unused `/analytics/direction-flow` endpoint), bar-chart upgrades for Events-by-camera/PPE-compliance, and a click-to-filter drill-down between them.
- **Declined**: gender/sex classification — no reliable classical-CV technique exists for it (unlike plates), and the user chose not to add a new ML dependency for it either. Not built, in any form.

## M24 — Hardening Round 2
**Ruff lint gate**: `ruff.toml` (repo root) tuned to preserve the codebase's own 3-tier import grouping (stdlib/third-party/`ibvap_common`/local) and allowlist FastAPI's `Depends`-family + `ibvap_common.auth.require_role` as immutable-default false positives. Repo-wide `ruff check .` passes clean. **Status: built and verified, still uncommitted** (no CI wiring yet, so it has zero enforcement effect either way — committing it is a pending decision, not a blocker).

**`system.health` WS topic**: `realtime-gateway` gained a `HealthPoller` that polls every service's `/health` every 15s and publishes `{service, status}` to the `system.health` Redis Pub/Sub channel *only on a status change* (not a polling firehose), bridged to the `system` WS topic. Also added `GET /api/v1/system/health` (viewer-gated) backed by the poller's own snapshot, since a WS topic only ever carries *future* changes — a client needs this once at connect time for current state. Wiring in a real REST route surfaced a real gap: realtime-gateway never registered the shared RFC7807 error handlers (WS-only before), so an unauthorized request 500'd instead of 401 — fixed. Frontend: Sidebar's "System Status" widget (`useSystemHealth` hook) now shows real checking/operational/degraded state instead of hardcoded "Operational" text, live-verified by stopping and restarting a real service and watching the Sidebar flip over the WS with no reload. **Status: committed and pushed** — `144d1f1` (ibvap `main`), `9393f8b` (Lux-frontend `Neha`).

**mypy --strict**: dry-run surfaced an estimated 250-350 fixes needed across all services for full compliance (largely real gaps, not just `ibvap_common` import noise once `py.typed` was added). **Status: scope decision still open** — asked the user twice, no answer given either time. Not resolved by this pass either; still needs an explicit call (full retrofit vs. "enforce only on new/touched files going forward" vs. skip).

**Security review** (2026-09-08): commissioned a full audit (RBAC coverage, internal-endpoint auth consistency, secrets hygiene) against every service's `app/api/*.py`. Findings and fixes:
- RBAC coverage: consistent everywhere except two real gaps found and fixed:
  - `GET /stream/{camera_id}/mjpeg` (ingestion-service) had **zero auth** — reachable by anyone with a camera_id, even though the endpoint that hands out its URL (`GET /cameras/{id}/stream`) is correctly gated. Since an `<img src>` tag can't carry an `Authorization` header, fixed with a new shared primitive instead of plain `require_role`: `ibvap_common/stream_auth.py` (`create_resource_token`/`verify_resource_token`, short-lived JWTs scoped to one `resource` string, reusing the existing `jwt_secret` rather than a new secret). `GET /cameras/{id}/stream` now mints one into the URL it returns (`Settings.stream_token_ttl_seconds`, default 300s); the mjpeg endpoint verifies it. 16 new unit tests in `libs/ibvap_common/tests/unit/test_stream_auth.py`; live-verified (no token / wrong-camera token / garbage token all → 401, real stream still plays in the browser).
  - `GET /media/recordings/{recording_id}` (media-service) had no auth at all and no frontend caller — added `require_role("viewer")`, zero blast radius.
- **Snapshot/recording static-auth gap — fixed as its own follow-up** (2026-09-08): `GET /media/snapshots/{id}` had the same missing-auth problem as the mjpeg route, but the actual bytes were served by nginx's `location /media/ { alias /data/media/; }` static block — **no auth at all, regardless of what the FastAPI route did** — so a plain `require_role` on the by-id route would've been security theater (and would've broken the two frontend `<img>`/`<video>` usages, which can't attach an `Authorization` header). While auditing this, also found event-alert-service independently leaking the same raw static paths: `Event.snapshot_url`/`recording_url` and `Alert.recording_url` are denormalized at capture time and were returned to the frontend verbatim on `GET /events/{id}`, `GET /alerts`, and the `event.new`/`alert.new`/`alert.updated` WS payloads — a second, independent bypass of any by-id-route auth, not previously flagged. Fixed end-to-end:
  - nginx: `location /media/` is now `internal;` — unreachable by any direct client request (verified: raw file path → 404). The regex by-id location (now also matching recordings' `/file` suffix) is the only way in.
  - `GET /media/snapshots/{id}` (media-service) verifies a `?token=` resource token (`stream_auth.py`, same primitive as mjpeg) scoped to that exact id, then serves the bytes itself via `X-Accel-Redirect` (no browser-visible redirect to the now-internal path). `GET /media/recordings/{id}` keeps its `require_role("viewer")` metadata response but its `playbackUrl` now points at a new token-gated `GET /media/recordings/{id}/file` sub-route (same shape, since that endpoint returns JSON metadata, not bytes).
  - `create_resource_token`/`verify_resource_token` gained a `build_resource_url` helper (`stream_auth.py`) so every issuing endpoint mints the token fresh at *read* time (not capture time — these are often viewed long after creation, unlike the mjpeg stream).
  - anpr-service's `GET /reads` and reid-service's search/matches endpoints now return `snapshotUrl` (a fetchable, token-scoped URL) alongside the existing bare `snapshotId`.
  - event-alert-service's `to_event_detail`/`to_alert_read` now ignore the denormalized raw `snapshot_url`/`recording_url` columns and rebuild signed URLs from the stored ids on every read instead (both the REST responses and the WS `event.new`/`alert.new`/`alert.updated` payloads).
  - 21 new unit tests across `ibvap_common`, media-service, anpr-service, reid-service, and event-alert-service (all passing). Live-verified against the running stack with real data: raw static snapshot/recording paths → 404; by-id routes with no/garbage/wrong-resource/expired token → 401; a real anpr-issued `snapshotUrl` and a real event-alert-issued `recordingUrl` both fetch successfully (200, correct `Content-Type`, `Accept-Ranges: bytes` preserved for video seeking) end-to-end through nginx.
  - **Not touched in this checkout**: the frontend (`Lux-frontend/src/pages/LicensePlates.jsx`, `PersonSearch.jsx`) isn't present in this repo — a live dev frontend at `localhost:5173` is clearly hitting this stack from elsewhere. Those `<img src>` usages need to switch from building a URL out of the bare `snapshotId` to using the new `snapshotUrl` field verbatim; flagged to the user, not fixed here.
- Internal-endpoint (`X-Internal-Token`) auth: zero findings — every true internal route checks it, and the shared comparison (`ibvap_common/internal_auth.py`) already uses `hmac.compare_digest` (constant-time).
- Secrets hygiene: zero hardcoded secrets found; `.env` correctly gitignored and not committed; one minor gap fixed — `GRAFANA_ADMIN_PASSWORD` had no `.env.example` entry (docker-compose silently falls back to the well-known default `admin` if unset) — added a documented placeholder.
- **Known gap, not addressed**: no rate-limiting middleware exists on any service's own API (nginx itself does have `limit_req` on a few routes, e.g. auth/camera — worth checking which routes are and aren't covered before assuming this is fully open).

## Next up
- Decide mypy --strict scope (see above — needs an explicit answer this time).
- Decide whether to commit the still-uncommitted ruff.toml/lint-cleanup and system.health work.
- Update the frontend's `LicensePlates.jsx`/`PersonSearch.jsx` (and anywhere else rendering a snapshot/recording) to use the new `snapshotUrl`/`recordingUrl`/`playbackUrl` fields instead of building a URL from the bare id.
- Rate-limiting audit/rollout (which routes nginx's existing `limit_req` actually covers, and closing the rest).
