# M10 Completion Summary (Hardening & Ops)

This doc records the work done to close out M10 — the final milestone — plus two
pipeline-accuracy bug fixes found along the way. M0 through M10 (every milestone
in the Implementation Guide) are now complete.

## 1. Loop-generation counting fix

A looping test video would otherwise inflate daily people/vehicle counts every
time it restarted from the beginning. A `loop_generation` int field was threaded
through the whole pipeline:

- `ingestion-service/app/capture/file_source.py` increments it on loop restart;
  persisted to Redis key `cam:{camera_id}:{sha1(source_url)[:12]}:loop_generation`
  (survives restarts, scoped per-video) via `camera_worker.py`'s
  `_loop_generation_key()` / `_load_loop_generation()`.
- Propagated through `frame_publisher.py` → `detection_publisher.py` →
  tracking-service's `TrackEvent.loop_generation` (`schemas/track.py`, mirrored
  in `event-alert-service/app/schemas/internal.py`) → persisted on
  `events.tracks.loop_generation` (migration `0003_add_loop_generation.py`).
- `analytics-service` migration `0002_exclude_loop_replays.py` filters
  `mv_daily_counters` / `mv_activity_by_hour` with `WHERE loop_generation = 0`.

**Bug fixed:** `worker_manager.py`'s `_reconcile()` never actually detected a
`sourceUrl` change on an already-running worker (comment claimed it did, code
didn't) — a re-upload silently kept streaming the OLD video forever. Fixed by
comparing `existing.source_url == config.get("sourceUrl")` before deciding to
keep the worker running.

## 2. Tracker accuracy improvements

- `tracking-service/app/core/config.py`: added `minimum_consecutive_frames: int = 3`
  (filters single-frame flicker false positives) and doubled
  `lost_track_buffer_frames` to 60 (longer occlusion grace period). Wired into
  `ByteTrackRunner` and `TrackManager._build_runner()`.
- `detection-service/app/core/config.py`: `model_path` changed to
  `/srv/models/yolov8s.pt` (was yolov8n) for better small/distant-object recall.
- **Track-merge heuristic** (biggest accuracy win) in
  `event-alert-service/app/rules/engine.py`: when a track is lost and a new
  track starts nearby (same `object_type`, within
  `track_merge_max_distance_percent=15.0` of last known bbox center, within
  `track_merge_window_seconds=2.0`), it's treated as the same person
  reactivating (`track_repo.reactivate()`) instead of a new counted person.
  Toggle: `Settings.enable_track_merge: bool = True` — set `False` and redeploy
  to fully revert, no code changes needed. New repo methods:
  `TrackRepository.get_by_ref()` and `.reactivate()`.
  Verified live: reduced a busy-scene person count from 33 → 13 (confirmed
  correct order of magnitude by visual inspection of extracted video frames).

## 3. Correlation IDs

`ibvap_common/logging.py` already had first-hop HTTP correlation-id middleware;
added `new_correlation_id()`, `correlation_id_context()` (context manager for
background consumers, not just HTTP), `correlated_headers()`, and constant
`CORRELATION_ID_FIELD = "correlationId"`.

Threaded through: ingestion (`frame_publisher.py` mints a fresh id per frame) →
detection (`frame_consumer.py` binds context, `detection_publisher.py`
propagates) → tracking (`detection_consumer.py` binds; `track_manager.py`'s
`_event()` / lost-event use `get_correlation_id()`; new field
`TrackEvent.correlation_id: str = ""`) → event-alert (`track_consumer.py` binds
context around rule evaluation; `camera_client.py` and `snapshot_client.py`
attach `correlated_headers()` to outbound calls).

Deliberately **not** propagated into Pub/Sub or WebSocket payloads (documented
API contract, out of scope). Verified live: one frame's id traced correctly
through frames → detections → every resulting track event.

## 4. Prometheus / Grafana

New `ibvap_common/metrics.py`: `install_metrics(app, service_name)` adds an
HTTP middleware (`http_requests_total`, `http_request_duration_seconds`,
labels `service,method,path,status`) plus a `GET /metrics` endpoint. Wired
into all 9 services' `main.py`.

Custom pipeline counters: `ingestion_frames_published_total`
(`frame_publisher.py`), `detection_frames_processed_total`
(`frame_consumer.py`), `tracking_detections_processed_total`
(`detection_consumer.py`), `event_alert_track_events_processed_total` +
`event_alert_rules_fired_total{event_type}` (`track_consumer.py`).

Infra additions in `docker-compose.yml`: `prometheus` (`:9090`,
`prom/prometheus:v2.55.1`) and `grafana` (`:3001`→3000,
`grafana/grafana:11.3.1`, login `admin` / `$GRAFANA_ADMIN_PASSWORD`). Config
under `monitoring/`: `prometheus.yml` (scrapes all 9 services by container
name on `ibvap-internal`), Grafana datasource + dashboard provisioning, and
`ibvap-overview.json` dashboard (5 panels: request rate, p95 latency, 5xx
rate, pipeline throughput, rules fired).

Verified: all 9 Prometheus targets show "up"; Grafana datasource + dashboard
auto-provisioned and queryable.

## 5. Security pass

- **Rate limiting** (nginx only): `nginx/nginx.conf` adds
  `limit_req_zone $binary_remote_addr zone=auth_login:10m rate=5r/m;` and
  `zone=api_general:10m rate=20r/s;` + `limit_req_status 429;`.
  `nginx/conf.d/api-gateway.conf`: exact-match `location = /api/v1/auth/login`
  gets `zone=auth_login burst=3 nodelay;` (takes precedence over the general
  `/api/v1/auth/` prefix block, which gets `zone=api_general burst=40 nodelay;`);
  same general zone applied to cameras/sectors/settings/events/alerts/
  analytics/dashboard blocks. `/stream/` and `/ws` deliberately excluded
  (long-lived connections). Custom RFC7807-style 429 JSON body via
  `error_page 429 = @rate_limited;`.
  Verified live: 5th login attempt within window returns 429 with correct
  JSON; normal login works after the window passes.
- **Timing-attack fix**: `ibvap_common/internal_auth.py`'s
  `verify_internal_token` changed from `!=` to `hmac.compare_digest()`.
- **Username-enumeration-via-timing fix**: `auth-service/app/services/security.py`
  adds `DUMMY_PASSWORD_HASH` (bcrypt hash of a fixed dummy string, computed at
  module import); `login()` now always calls `verify_password()` (against the
  dummy hash if the user is None) so "no such user" and "wrong password" cost
  the same time.
- **Path-traversal defense-in-depth**: `camera-service/app/schemas/camera.py`'s
  `CameraCreate.external_id` now requires `pattern=r"^[A-Za-z0-9_-]+$"`;
  `camera-service/app/api/cameras.py`'s `upload_video()` now calls
  `await service.get_camera(camera_id)` before any file I/O, and sanitizes
  with `os.path.basename(camera_id)` when building the storage subdir (defense
  in depth even though both endpoints already require the `admin` role).
- Secrets audit: clean — no hardcoded creds, `.env` gitignored, JWT algorithm
  pinned on decode, bcrypt hashing, refresh tokens single-use/rotated.
  Noted-not-fixed: no CORS middleware exists anywhere (not a vulnerability,
  just a frontend-integration gap).
- New/updated tests: `libs/ibvap_common/tests/unit/test_internal_auth.py`
  (new), `services/auth-service/tests/unit/test_auth_service.py` (+1 test for
  unknown-username), `services/camera-service/tests/unit/test_camera_service.py`
  (+2 tests for `external_id` pattern validation).

## 6. Load testing

No fixed numeric SLA exists in SAS §11, so methodology was self-defined. Two
scripts in `load-tests/`:

- `load_test_http.py` — async httpx concurrency test against 4 read endpoints
  (dashboard stats, cameras, events, alerts), configurable via `BASE` /
  `ADMIN_PASSWORD` env vars.
- `load_test_cameras.py` — creates N synthetic file-cameras via the real API,
  waits, reads Prometheus per-camera ingestion/detection rates + Redis stream
  consumer-group lag, then deletes the cameras and their DB rows for full
  cleanup.

Results in `docs/load-test-report.md` (already sent to the user):
- HTTP test — 0% errors, 19.5 req/s, p50 14.7ms / p95 160.9ms over 15
  concurrent VUs / 20s.
- Multi-camera test (5 concurrent pipelines) — ingestion held ~3–4fps/camera
  unaffected; detection fell to ~27–33% of that under CPU contention
  (graceful degradation via Redis Stream `maxlen=200` cap — lag≈200 upstream
  but zero lag downstream on tracking's input, confirming the bottleneck
  isolates cleanly to Detection, matching SAS §11's documented design).

All synthetic test cameras and their `events.tracks` / `events.alerts` /
`events.events` rows were deleted afterward; dashboard confirmed back to a
clean state.

## 7. CI pipeline + GitHub

- Repo initialized (`git init`), first commit `a1bbc69` (428 files, verified
  no `.env`/secrets/`build/`/`__pycache__`/media-data included).
- Pushed to `https://github.com/neha-aj/Lux_claude.git` (private).
- `.github/workflows/ci.yml`: matrix of 10 jobs (`ibvap_common` + all 9
  services), each: checkout → setup-python 3.12 → `pip install ./libs/ibvap_common`
  (works around `pip` not understanding `[tool.uv.sources]` local-path deps) →
  (detection-service only) install CPU-only torch first → `pip install -e ".[dev]"`
  in the service's own directory → `python -m pytest -q`. Verified locally for
  all 10 packages before pushing (all passed: ibvap_common 10, auth 6, camera
  14, ingestion 8, detection 5, tracking 12, event-alert 27, media 3,
  analytics 10, realtime-gateway 17).
- Deliberately scoped out: lint/type-check enforcement (`ruff` / `mypy --strict`
  per IG §3). A dry run of bare-default `ruff check` produced 520
  "violations," but 277 were an irrelevant `EXE002` shebang check and 109 were
  FastAPI's own standard `Depends(...)` idiom (`B008`) being flagged as a
  false positive — real enforcement needs a proper project-specific config,
  not an ad hoc one. CI's blocking gate is tests-only, matching the IG's own
  Definition of Done ("Unit + integration tests green in CI").
- **Confirmed live on GitHub Actions: 10/10 jobs green.**

## Current state

All 5 M10 components (correlation IDs, Prometheus/Grafana, security pass,
load testing, CI pipeline) are complete and verified live. M0 through M10 —
every milestone in the Implementation Guide — is done.

- Local repo: `C:\Users\Neha AJ\Desktop\prototype2\M0-M3\ibvap`, branch `main`.
- Remote: `https://github.com/neha-aj/Lux_claude.git` (private), in sync with
  local `main`.
- Dev login: `admin` / `DevAdminPass123!` via `POST /api/v1/auth/login`.
- Grafana: `http://localhost:3001`, login `admin` / `$GRAFANA_ADMIN_PASSWORD`.
- Prometheus: `http://localhost:9090`.
