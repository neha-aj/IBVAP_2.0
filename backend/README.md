# IBVAP Backend

Implements every milestone in the Implementation Guide, **M0 (platform scaffolding) through M10 (Hardening & Ops)**. Everything here follows `/docs` exactly — read those first if anything here seems to deviate.

## What's implemented

| Milestone | Service | Status |
|---|---|---|
| M0 | docker-compose, nginx gateway, `ibvap_common` shared lib, Postgres schemas | ✅ |
| M1 | `auth-service` — login/refresh/logout/me, JWT, RBAC, bootstrap admin | ✅ |
| M2 | `camera-service` — camera CRUD, sectors, Settings page, **file upload / webcam registration** | ✅ |
| M3 | `ingestion-service` — opens file/webcam/rtsp sources, live MJPEG preview, Redis Stream frame publishing, camera health/status heartbeat | ✅ |
| M4 | `detection-service` — YOLOv8 inference on `cam:{id}:frames`, normalized bbox output, `cam:{id}:detections` stream + current-detections cache; `GET /cameras/{id}/detections/current` (camera-service) reads it | ✅ |
| M5 | `tracking-service` — ByteTrack on `cam:{id}:detections`, persistent `trackId`s, `track.started`/`track.updated`/`track.lost` lifecycle events on `cam:{id}:tracks`; `detections/current` now carries a stable `trackId` instead of `null` | ✅ |
| M6 | `event-alert-service` — rule engine (count thresholds, camera-offline, loitering dwell-time, zone intrusion) consuming `cam:{id}:tracks` + `camera.status_changed`, persists `events`/`alerts` to Postgres, `GET/PATCH /events`, `GET/PATCH /alerts`, emits `event.new`/`alert.new`/`alert.updated` over Redis Pub/Sub | ✅ |
| M7 | `media-service` — snapshot capture/storage/retrieval; every event/alert now captures a real snapshot at trigger time (`snapshotUrl` resolvable, survives restart via the persisted `media-data` volume) | ✅ |
| M8 | `realtime-gateway` — single WS endpoint (`/ws?token={jwt}`), topic subscription (`alerts`, `events`, `camera:{id}`), bridges `event.new`/`alert.new`/`alert.updated`/`camera.status_changed`/`detection.new` from Redis Pub/Sub to connected clients | ✅ |
| M9 | `analytics-service` — 5 materialized views refreshed every 60s (`REFRESH MATERIALIZED VIEW CONCURRENTLY`), `GET /dashboard/stats` (all 6 StatCards) + 5 `/analytics/*` chart endpoints, short-TTL Redis cache in front | ✅ |
| M10 | Hardening & Ops — correlation IDs, Prometheus/Grafana, security pass, load testing, and CI (all 10 jobs green on GitHub Actions) | ✅ |

## Run it

```bash
cp .env.example .env
# edit .env: set real JWT_SECRET, POSTGRES_PASSWORD, BOOTSTRAP_ADMIN_PASSWORD, INTERNAL_SERVICE_TOKEN

docker compose up --build
```

This starts Postgres, Redis, NGINX (port 8080), `auth-service`, `camera-service`, `ingestion-service`, `detection-service`, `tracking-service`, `event-alert-service`, `media-service`, `realtime-gateway`, and `analytics-service`. Each service applies its own Alembic migrations on startup, and `auth-service` creates a bootstrap admin user (`BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` from `.env`) if the `users` table is empty. `detection-service` downloads YOLOv8n weights on first inference call (needs outbound internet the first time; cached in the `detection-models` volume after) — its healthcheck has a 60s `start_period` to allow for this.

## Smoke test (M1 + M2 completion criteria)

```bash
# 1. Log in as the bootstrap admin
curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<BOOTSTRAP_ADMIN_PASSWORD>"}' | tee /tmp/login.json

TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/login.json'))['accessToken'])")

# 2. Create a camera backed by a video file you have on hand
curl -s -X POST http://localhost:8080/api/v1/cameras \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"North Gate Test","location":"Sector A","sector":"Alpha","type":"file"}' | tee /tmp/camera.json

CAMERA_ID=$(python3 -c "import json;print(json.load(open('/tmp/camera.json'))['id'])")

# 3. Upload the actual video for that camera
curl -s -X POST "http://localhost:8080/api/v1/cameras/$CAMERA_ID/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/your/test-video.mp4;type=video/mp4"

# 4. List cameras -- exact shape the frontend's mockCameras uses
curl -s http://localhost:8080/api/v1/cameras -H "Authorization: Bearer $TOKEN"

# 5. Register a live webcam instead (no file upload -- source_url is the device URI/index)
curl -s -X POST http://localhost:8080/api/v1/cameras \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Laptop Webcam","location":"Office","type":"webcam","sourceUrl":"0"}'

# 6. Settings page data
curl -s http://localhost:8080/api/v1/settings -H "Authorization: Bearer $TOKEN"
```

## Smoke test (M3 completion criteria)

M3 is where cameras actually come alive. Continuing from the steps above:

```bash
# 7. Within ~1-2 seconds of the upload completing, ingestion-service should have
#    picked the camera up (it polls every CAMERA_REFRESH_INTERVAL_SECONDS, default 15s
#    -- or restart ingestion-service to force an immediate poll) and opened the file.
#    Check its status flipped from "offline":
curl -s "http://localhost:8080/api/v1/cameras/$CAMERA_ID" -H "Authorization: Bearer $TOKEN"
# expect: "status": "online" (or "warning" if the measured fps is low), "fps": <nonzero>

# 8. Watch the live preview -- this is a real MJPEG stream, open it directly in a browser:
#    http://localhost:8080/stream/<CAMERA_ID>/mjpeg
#    or fetch the URL from the API (this is what the frontend will call):
curl -s "http://localhost:8080/api/v1/cameras/$CAMERA_ID/stream" -H "Authorization: Bearer $TOKEN"

# 9. Disconnect it: delete the camera (or stop docker compose) and confirm the
#    worker stops and the ingestion service's /ready count drops:
curl -s http://localhost:8080/health/ingestion
```

For a webcam camera (created in step 5), ingestion-service opens the actual device -- on Linux, uncomment the `devices:` mapping for `ingestion-service` in `docker-compose.yml` (e.g. `/dev/video0:/dev/video0`) first, or it will fail to open and the camera will stay `offline`.

## Smoke test (M4 completion criteria)

Continuing from a camera created/uploaded above (steps 1-3):

```bash
# 10. Give detection-service a few seconds to discover the camera (polls every
#     CAMERA_REFRESH_INTERVAL_SECONDS, default 15s) and run inference on its
#     frames, then check the live overlay data:
curl -s "http://localhost:8080/api/v1/cameras/$CAMERA_ID/detections/current" -H "Authorization: Bearer $TOKEN"
# expect: [] while no objects are in frame, or an array of
# {id, cameraId, type: "person"|"vehicle", confidence, trackId: null, bbox: {x,y,width,height}}
# (bbox values are percentages 0-100, not pixels) once the test video shows one.

# 11. Confirm it's really consuming cam:{id}:frames end-to-end:
curl -s http://localhost:8080/health/detection
```

`trackId` stayed `null` at M4; from M5 onward it's a stable id. If the test video has no people/vehicles in frame, `detections/current` will correctly return `[]` -- use a clip with visible people/cars to see boxes.

## Smoke test (M5 completion criteria)

Continuing from the same camera:

```bash
# 12. Poll detections/current a few times in a row -- trackId should now be a
#     real, non-null value that stays THE SAME for the same person/vehicle
#     across calls (it only changes if they leave frame long enough to be
#     forgotten, or a new object appears):
curl -s "http://localhost:8080/api/v1/cameras/$CAMERA_ID/detections/current" -H "Authorization: Bearer $TOKEN"

# 13. Confirm tracking-service is alive and consuming:
curl -s http://localhost:8080/health/tracking
```

There's no public REST endpoint for the raw lifecycle events (`track.started`/`track.updated`/`track.lost`) -- inspect the `cam:{id}:tracks` Redis Stream directly if you want to see them: `docker exec ibvap-redis-1 redis-cli XRANGE cam:<CAMERA_ID>:tracks - +`.

## Smoke test (M6 completion criteria)

The easiest rule to trigger on demand is the person-count threshold (default: more than 5 people at once) or camera-offline. Continuing from the same camera:

```bash
# 14. Trigger "Connection Lost". A real offline transition only fires from a
#     source that actually stops producing frames -- a looping file camera
#     (loop_file_sources=true, the default) never does that naturally, and
#     deleting the camera removes its row before the worker's offline report
#     can land (a real race, not by design). The deterministic way to
#     exercise this rule: publish the same message camera-service publishes
#     on a real transition, directly:
docker exec ibvap-redis-1 redis-cli PUBLISH camera.status_changed "{\"cameraId\":\"$CAMERA_ID\",\"status\":\"offline\"}"

# 15. Within one poll interval, a row should appear in both:
curl -s "http://localhost:8080/api/v1/events?eventType=Connection%20Lost" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:8080/api/v1/alerts?status=active" -H "Authorization: Bearer $TOKEN"

# 16. Acknowledge it (requires operator role or higher -- the bootstrap admin
#     qualifies) and confirm acknowledgedBy/acknowledgedAt got set server-side:
ALERT_ID="<id from step 15>"
curl -s -X PATCH "http://localhost:8080/api/v1/alerts/$ALERT_ID/status" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"resolved"}'

# 17. Confirm event-alert-service is alive and consuming:
curl -s http://localhost:8080/health/event-alert
```

To see the loitering and zone-intrusion rules fire, a track needs to stay in frame past `LOITERING_SECONDS_THRESHOLD` (default 30s) or cross into a configured zone -- zones have no public create API yet (Phase 2, per Implementation Guide §11), so exercising that rule requires inserting a test row directly:

```bash
docker exec ibvap-postgres-1 psql -U ibvap -d ibvap -c \
  "INSERT INTO camera.zones (id, camera_id, name, polygon, zone_type) SELECT gen_random_uuid(), id, 'Test Perimeter', '[{\"x\":0,\"y\":0},{\"x\":100,\"y\":0},{\"x\":100,\"y\":100},{\"x\":0,\"y\":100}]'::jsonb, 'perimeter' FROM camera.cameras WHERE external_id = '$CAMERA_ID';"
```
(That polygon covers the whole frame, so the very next tracked object should trigger "Fence Intrusion".)

## Smoke test (M7 completion criteria)

Continuing from a camera actively streaming (so ingestion-service has a cached frame to hand over):

```bash
# 18. Trigger any rule (e.g. the offline-alert command from step 14, or wait
#     for a real one), then fetch that event's detail -- snapshotUrl should
#     now be a real, resolvable path, not null:
EVENT_ID="<id from GET /events>"
curl -s "http://localhost:8080/api/v1/events/$EVENT_ID" -H "Authorization: Bearer $TOKEN"

# 19. Open the snapshot directly in a browser (no auth needed, same as the
#     MJPEG stream) -- either the URL from step 18, or via the lookup-by-id
#     API (307 redirect to the same place):
#     http://localhost:8080<snapshotUrl from step 18>

# 20. Confirm it survives a restart (persisted volume, not the container's
#     own filesystem):
docker compose restart media-service
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8080<snapshotUrl>"
# expect: 200

# 21. Confirm media-service is alive and its DB is reachable:
curl -s http://localhost:8080/health/media
```

If step 18's `snapshotUrl` is null, the camera likely wasn't actively streaming (no cached frame in ingestion-service) at the exact moment the rule fired -- capture is intentionally best-effort (SAS §11) and never blocks the event itself.

## Smoke test (M8 completion criteria)

No shell one-liner for a WebSocket client, so a tiny Python script (needs `pip install websockets`):

```python
import asyncio, json, websockets

TOKEN = "<accessToken from step 1>"
CAMERA_ID = "<CAMERA_ID from step 2>"

async def main():
    async with websockets.connect(f"ws://localhost:8080/ws?token={TOKEN}") as ws:
        await ws.send(json.dumps({"action": "subscribe", "topics": ["alerts", "events", f"camera:{CAMERA_ID}"]}))
        while True:
            print(await ws.recv())

asyncio.run(main())
```

Run that, then in another terminal fire the same offline-alert trigger from step 14 (or wait for `detection.new` to arrive on its own while the camera streams) -- you should see `{"event": "alert.new", "data": {...}}`, `{"event": "event.new", "data": {...}}`, and (if the camera has visible people/vehicles) `{"event": "detection.new", "data": {...}}` messages print, each within one pipeline cycle of the underlying trigger. Also:

```bash
# Confirm realtime-gateway is alive and report a connection count:
curl -s http://localhost:8080/health/realtime
```

A missing/invalid `token` query param closes the connection immediately (WS close code 4401) -- try connecting without one to confirm.

## Smoke test (M9 completion criteria)

```bash
# 22. All six Dashboard StatCards in one call:
curl -s http://localhost:8080/api/v1/dashboard/stats -H "Authorization: Bearer $TOKEN"

# 23. The four Analytics charts + the inline events-by-camera list:
curl -s "http://localhost:8080/api/v1/analytics/activity-overview?range=today" -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8080/api/v1/analytics/activity-weekly -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8080/api/v1/analytics/alerts-by-type -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8080/api/v1/analytics/camera-uptime -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8080/api/v1/analytics/events-by-camera -H "Authorization: Bearer $TOKEN"

# 24. Confirm analytics-service is alive and its DB is reachable:
curl -s http://localhost:8080/health/analytics
```

If a camera has never been created, `activeCameras`/`totalCameras`/`camera-uptime` correctly read as `0`/`0`/`[]` -- there's nothing to aggregate yet, not a bug. Create/upload a camera (steps 1-4) and wait ~15s (ingestion picks it up) plus up to 60s (the next scheduled view refresh -- `REFRESH_INTERVAL_SECONDS`) to see it appear. To verify against manually-computed values (the milestone's own completion criterion): `peopleDetectedToday`/`vehiclesDetectedToday` should equal the number of *distinct* `trackId`s (not raw detection frames) seen today across all cameras -- cross-check by counting distinct `trackId`s from `cam:{id}:tracks` (`docker exec ibvap-redis-1 redis-cli XRANGE cam:<CAMERA_ID>:tracks - +`) or the events database directly (`docker exec ibvap-postgres-1 psql -U ibvap -d ibvap -c "SELECT object_type, count(*) FROM events.tracks WHERE first_seen::date = current_date GROUP BY object_type;"`).

## Run tests

Each service's unit tests use in-memory fakes (no live DB or hardware required, except `ingestion-service`'s capture-factory tests which need OpenCV installed, `detection-service`'s tests which only exercise the pure bbox-normalization logic, and `tracking-service`'s tests which run the real ByteTrack algorithm -- none of these pull in torch/GPU or live infra at test time -- all are normal dependencies, so `pip install -e ".[dev]"` pulls in what's needed):

```bash
cd services/auth-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/camera-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/ingestion-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/detection-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/tracking-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/event-alert-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/media-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/realtime-gateway && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
cd services/analytics-service && pip install -e ".[dev]" -e ../../libs/ibvap_common && pytest
```

## Connecting the frontend

Point `src/services/api.js`'s base URL at `http://localhost:8080/api/v1`, forward the JWT from `/auth/login` as `Authorization: Bearer <token>`, and `cameraService.getAll()` can call `GET /cameras` directly — the response shape matches `mockCameras` field-for-field (see `docs/01-Frontend-Analysis-Report.md` §5 and `docs/04-API-Specification.md` §2). For the Surveillance page's live view, point `VideoPlaceholder`'s slot at an `<img src="http://localhost:8080/stream/{camera.id}/mjpeg">` once `GET /cameras/{id}/stream` returns a real camera. There's no login page in the frontend yet (per the Frontend Analysis Report, that's an acknowledged gap) — for now you can fetch a token via curl/Postman as shown above and hardcode it in `api.js` while developing, or add a minimal login form.

## M4 notes / deviations

- `GET /detections` (API Spec §4, historical read path) is **not** implemented yet. Per DB Spec §3, the underlying `events.detections` table is owned by the Event/Alert Service (M6) -- there is no persistence target for it until then. M4's own completion criteria (Implementation Guide §1) only require the live `detections/current` cache and normalized bbox stream, both of which are done.
- Default inference backend is Ultralytics YOLOv8 (`yolov8n.pt`) via torch, CPU by default and GPU-automatic if CUDA is present -- this covers the "GPU if available" half of SAS §5.2/§9 in one code path. A real ONNX Runtime backend (`app/inference/onnx_runner.py`) also exists and is used automatically instead if a `.onnx` model is dropped into the mounted `detection-models` volume (`ONNX_MODEL_PATH`, default `/srv/models/yolov8n.onnx`) -- this keeps the default image from requiring an extra, separate model-export pipeline while still providing a real, working no-torch CPU path for anyone who wants it. `Dockerfile.gpu` is provided per `docs/06-Project-Structure.md` but untested here (no GPU on the dev machine this was built on).

## M5 notes / deviations

- No new REST endpoints. Per the API Specification there isn't one for tracks -- M5's only externally-visible change is `trackId` becoming non-null in the existing `detections/current` shape. Lifecycle events land only on the `cam:{id}:tracks` Redis Stream (as the SAS specifies); a REST/WebSocket read path for them is Event/Alert Service's (M6) job, per the module dependency chain in Implementation Guide §2.
- `detection-service` (M4) keeps writing `cam:{id}:current_detections` with `trackId: null` as before; `tracking-service` overwrites the same key with the enriched (real `trackId`) version shortly after. This is deliberate layered degradation (SAS §11): if tracking-service falls behind or crashes, the overlay still works, just without stable ids, rather than going stale or empty.
- `sv.ByteTrack` (from the `supervision` package) is deprecated upstream as of 0.28.0 with removal planned for 0.31.0 and no replacement class named yet -- pinned to `<0.31` so a routine dependency bump can't silently break tracking. Worth revisiting when upstream's replacement API is announced.

## M6 notes / deviations

- **`camera.status_changed` Pub/Sub channel added.** SAS §5.4 names this as an Event/Alert Service input, but nothing published it before M6 (camera-service only pushed status via an internal HTTP call). `camera-service`'s `update_status` now also publishes to this channel on a real transition (not every heartbeat) -- new plumbing this milestone genuinely needed, not a redesign of anything M2/M3 already did.
- **`camera_id` stored as the external_id string, not a UUID.** DB Spec §3 types `events.{events,alerts,tracks}.camera_id` as `uuid` (`camera.cameras.id`), but every actual producer in the running pipeline -- Redis streams, Tracking Service's `TrackEvent`, camera-service's own public `id` field -- already uses the external_id string as "the" camera id throughout. Matching that avoids an unused resolve-to-UUID round-trip on every single event write for a join that nothing in this schema ever needs.
- **`camera_name` denormalized onto `events`/`alerts`** alongside the already-documented `location` column, for the same reason `location` was denormalized (API responses need it inline; DB Spec §6 explicitly allows denormalizing "when the frontend contract requires it").
- **Zones are read, not writable.** `camera.zones` (scaffolded in M2, unused until now) gets a new internal-only read endpoint (`GET /internal/cameras/{id}/zones`) so the intrusion rule has real data to query -- no public create/edit API, since that's explicitly Phase 2 (Implementation Guide §11). The rule correctly fires zero events until a zone is configured; see the smoke test above for inserting one manually to verify it works.
- **`events.detections` (raw per-frame detection history) and its `GET /detections` read path are still deferred**, now past M6 too. It's not part of M6's own completion criteria, and implementing it would mean a second high-volume consumer (every detection frame, not just track lifecycle transitions) for a page the Frontend Analysis Report doesn't actually name. Revisit if a real need for historical detection queries shows up.
- **Fixed a latent M5 bug while building this**: `tracking-service`'s `track.lost` events always hardcoded `object_type="person"`; M6's per-type active-count rule depends on this being correct (a lost vehicle track was being silently misfiled), so `TrackManager` now remembers each track's real type across its lifecycle. Covered by a new regression test in `tracking-service`.

## M7 notes / deviations

- **A real routing collision, resolved.** The API Spec puts `GET /media/{snapshots,recordings}/{id}` at the bare `/media/` path (no `/api/v1` prefix, unlike every other service) -- but nginx has served `/media/` as a static-file alias since M2 (for camera video uploads), and the actual stored snapshot files also live under `/media/snapshots/{cameraId}/{date}/{file}.jpg`. Resolved with a regex location matching a UUID-shaped last path segment (the API lookup-by-id) ahead of the generic static alias (everything else, since `cameraId` is never UUID-shaped) -- see the comment in `nginx/conf.d/api-gateway.conf`.
- **New internal endpoint on `ingestion-service`**: `GET /internal/cameras/{id}/snapshot` returns the camera's current cached frame as a raw JPEG. SAS §5.5.2 says "Detection/Ingestion service encodes the relevant frame... sends to Media Storage Svc" -- Ingestion already re-encodes every captured frame to JPEG for its own MJPEG preview cache, making it the cheaper integration point of the two.
- **Snapshot capture wired into event creation, not made a separate async step.** `event-alert-service` now calls Ingestion for the current frame and Media Storage to store it synchronously as part of persisting an event, before publishing `event.new` -- matching "Alert/event creation always has a resolvable snapshotUrl" (Implementation Guide §1) literally: "always" reads as "at creation time," not eventually-consistent. Both calls are best-effort (SAS §11): any failure (camera not actively streaming, either service briefly down) leaves `snapshotId`/`snapshotUrl` null rather than blocking or failing the event itself, which is already persisted by that point.
- **`snapshot_url` denormalized onto `events.events`** alongside `snapshot_id`, same rationale as `camera_name`/`location` in M6 -- avoids a live cross-service call on every `GET /events/{id}`.
- **Recordings are schema-only**, per the Implementation Guide: M7's completion criteria only mention snapshots. `GET /media/recordings/{id}` is fully real against the `media.recordings` table (Frontend Analysis Report's own "expose the endpoints now" philosophy), but nothing in the pipeline has a documented trigger for segment recording yet (unlike snapshots' three documented triggers, SAS §5.5.1), so the table stays empty until a future milestone adds a producer.
- **Camera-service's own video-upload storage is untouched.** Its `storage/backend.py` docstring already says uploads "should be proxied [to Media Storage] once M7 lands" -- that's a refactor of already-working M2 functionality, not part of M7's own completion criteria, so left for a dedicated pass rather than folded in here.
- **`GET /cameras/{id}/snapshot`** (API Spec §2, camera-service) is still not implemented -- it implies a "latest snapshot" per camera, which needs periodic-thumbnail-refresh (SAS §5.5.1 trigger (c)), a scheduler this milestone doesn't build. Not part of M7's completion criteria either.

## M8 notes / deviations

- **`detection.new` had no publisher until now.** API Spec §8 documents it as a WebSocket event, but nothing in M4/M5 published it -- M4/M5's own completion criteria only required the `detections/current` REST cache, not a push channel, and there was no subscriber for it to matter until this milestone. `tracking-service`'s `TrackPublisher` (the final, track-enriched stage) now also publishes it to Redis Pub/Sub, once per non-empty detection batch per camera.
- **Per-camera topic routing, not one firehose.** `alerts` and `events` are global topics (any subscriber gets every message), but `camera.status_changed` and `detection.new` are routed only to clients subscribed to that specific `camera:{id}` topic -- `detection.new` in particular fires up to 5x/sec per active camera, and blasting every camera's detections to every connected client regardless of what they're viewing would be pure waste at any real scale. The gateway still receives all per-camera messages on one Redis subscription (Phase 1 single-node scale, matching the SAS's own reasoning for choosing Pub/Sub over a heavier broker) and filters gateway-side.
- **No message history/replay.** Per SAS §5.1 (Pub/Sub is "at-most-once... WS clients that miss a push get consistency back via REST refetch"), a client that connects after a message fired simply misses it -- by design, not an oversight. Every pushed event has a REST source of truth it can re-fetch from.
- **`system.health` is unimplemented.** API Spec §8 marks it "(optional, ops use)" and it's absent from M8's own completion criteria (which name only `alert.new`/`event.new`/`camera.status_changed`/`detection.new`) -- no service publishes service-health-change events, so this topic exists in name only, ready for a future milestone to wire a producer.

## M9 notes / deviations

- **Reads across schemas directly, by design.** Unlike every other service, `analytics-service` queries `camera.cameras`, `camera.camera_health`, `events.tracks`, `events.events`, and `events.alerts` with plain cross-schema SQL rather than internal API calls. This is explicitly sanctioned in SAS §3's own architecture table ("Analytics Service | ... | Postgres (reads across schemas via views)") -- bulk aggregation over raw pipeline tables via one API call per row isn't practical, and a read-only view carries none of the coupling risk a cross-schema write or foreign key would.
- **`peopleDetectedToday`/`vehiclesDetectedToday` count distinct tracked objects, not raw detections.** Sourced from `events.tracks` (one row per `track.started`), not the per-frame `cam:{id}:detections` stream -- counting frames would count the same person once per inference cycle for as long as they're in view (5x/sec), wildly overcounting. This was the actual gap a user flagged mid-session: there was no historical/aggregate count anywhere before this milestone, only the live `detections/current` snapshot.
- **`camera.camera_health` populated for the first time.** Scaffolded since M2 ("table exists now so M3 has nothing to migrate") but nothing ever wrote to it -- M3 through M8 had no need for a heartbeat *history*, only the current status. `camera-service`'s `update_status` now records one row per heartbeat (not just transitions), giving `mv_camera_uptime` a real time-series to compute from.
- **`activity-weekly` isn't one of DB Spec §5's five named materialized views.** It's a live `GROUP BY` over the already-tiny, already-pre-aggregated `mv_daily_counters` (one row per day ever recorded) computed at read time -- still fast without a sixth view for what's a cheap derived query.
- **`alerts-by-type` groups by the rule engine's actual alert types** ("Fence Intrusion", "Connection Lost", "Loitering Detected", "Restricted Zone Entry" -- see M6), not the API Spec's illustrative example categories ("Intrusion/Vehicle/Loitering/Other"), which aren't a fixed enum anywhere in the spec.
- **`eventsTodayDeltaPct` reads `0.0` until there's at least one prior day of history** to average against (a brand-new install, or right after a fresh `docker compose up` with an empty database) -- guards divide-by-zero rather than showing a misleading spike.

## M0-M9 complete

M0 through M9 -- every milestone in `docs/03-Implementation-Guide.md` §1 is now built, tested, and verified live against the running stack.

## M10 complete (Hardening & Ops)

Per the Implementation Guide's five M10 components:

| Component | Status |
|---|---|
| Structured logging correlation IDs | ✅ propagated end-to-end |
| Prometheus/Grafana metrics | ✅ live, all 9 services scraped |
| CI pipeline | ✅ done -- all 10 jobs green on GitHub Actions |
| Load testing | ✅ done |
| Security pass (rate limiting, secrets audit) | ✅ done |

**Correlation IDs now propagate the whole way through** (SAS §10: "correlation ID propagated from Gateway through every downstream call and into pipeline messages") -- previously `ibvap_common.logging.install_correlation_id_middleware` only covered the first hop (client → one service); it died there. Now:

- `ingestion-service` mints a fresh id per captured frame (there's no inbound request to inherit one from) and includes it on the `cam:{id}:frames` Stream message.
- `detection-service` reads it off the frame, binds it for the duration of that frame's inference (`ibvap_common.logging.correlation_id_context` -- a new context manager for binding an id inside a background consumer loop, not just an HTTP request), and re-publishes it on `cam:{id}:detections`.
- `tracking-service` does the same, threading it into every `TrackEvent` (`loop_generation`'s sibling field) on `cam:{id}:tracks`.
- `event-alert-service` binds it while evaluating rules for that event, so its own outbound calls to `camera-service` (zone/camera-info lookups) and `ingestion-service`/`media-service` (snapshot capture) carry it as an `X-Correlation-ID` header via the new `ibvap_common.logging.correlated_headers()` helper.

Verified live: one frame's id was traced from its `cam:{id}:frames` entry through the matching `cam:{id}:detections` entry into every `TrackEvent` its detections produced on `cam:{id}:tracks` -- all sharing the same id, distinct from every other frame's.

Deliberately **not** propagated into the `event.new`/`alert.new`/`alert.updated` Redis Pub/Sub payloads or the WebSocket envelope -- those are documented, frontend-facing contracts (API Spec §8), and adding a field there would be a real (if additive) change to a shape other code already depends on. The internal Streams pipeline and internal HTTP calls above are where tracing actually matters for debugging a stuck/slow request; Pub/Sub payloads are already tied to a specific persisted `event`/`alert` id that serves the same tracing purpose end-to-end.

**Prometheus/Grafana are live** (`docker-compose.yml` adds `prometheus` on `:9090` and `grafana` on `:3001`, login `admin` / `$GRAFANA_ADMIN_PASSWORD`):

- Every service gets baseline HTTP metrics for free via the new `ibvap_common.metrics.install_metrics(app, service_name)` -- request count, latency histogram, all labeled by service/method/path/status -- plus a `GET /metrics` endpoint, wired in identically to `install_correlation_id_middleware`/`install_error_handlers` in every service's `main.py`.
- Since most of the real work in `ingestion`/`detection`/`tracking`/`event-alert-service` happens in background Redis Streams consumers, not HTTP handlers, each also defines its own `prometheus_client.Counter` at the natural point in its own pipeline: `ingestion_frames_published_total`, `detection_frames_processed_total`, `tracking_detections_processed_total`, `event_alert_track_events_processed_total`, `event_alert_rules_fired_total` (labeled by `event_type`).
- `monitoring/prometheus.yml` scrapes all 9 services by container name on the shared `ibvap-internal` network; `monitoring/grafana/provisioning/` auto-registers the Prometheus datasource and a starter "IBVAP Overview" dashboard (request rate, p95 latency, 5xx rate, pipeline throughput, rules fired by type) on first boot -- no manual Grafana setup needed.
- Verified live: all 9 targets show `up` in Prometheus, the dashboard/datasource are provisioned and queryable, and a real pipeline counter (`ingestion_frames_published_total`) reflects genuine frame-publish activity from the running camera.

**Security pass complete** -- an audit (secrets handling, auth flows, file-upload paths) plus rate limiting. Findings and fixes:

- **Rate limiting, at the gateway** (`nginx/nginx.conf` + `nginx/conf.d/api-gateway.conf`) -- one place for all 9 services rather than middleware repeated in each. `POST /api/v1/auth/login` gets its own strict zone (5 req/min/IP, burst 3 -- brute-force protection); every other public API path gets a much more generous general zone (20 req/s/IP, burst 40); `/stream/` (MJPEG) and `/ws` (WebSocket) are deliberately excluded -- they're long-lived connections, not repeated discrete requests, so a request-rate limit doesn't apply to them. A rate-limited request gets a `429` with a body matching the rest of the API's RFC 7807 problem+json shape, not nginx's default HTML error page. Verified live: hammering `/auth/login` starts returning `429` after the 4th attempt within the window; a normal login still succeeds once the window passes.
- **Internal service-to-service token comparison wasn't constant-time** (`ibvap_common.internal_auth.verify_internal_token` used Python's `!=` on the raw token strings, which short-circuits at the first differing byte -- a timing side-channel in principle). Fixed with `hmac.compare_digest`.
- **Login could time-enumerate valid usernames** -- a nonexistent username short-circuited past the bcrypt check entirely (`user is None or not verify_password(...)`), so "no such user" returned measurably faster than "wrong password". Fixed in `auth-service`: always run `verify_password` -- against a real dummy hash when there's no user to check against -- so both paths cost the same.
- **`camera_id`/`external_id` could reach a filesystem path unsanitized.** `POST /cameras/{id}/upload` built its storage subdirectory from the raw URL path segment *before* confirming the camera even exists, and `external_id` (settable at camera creation, admin-only) had no character restriction at all -- both are meant to end up as `uploads/{id}/...` on disk. Fixed three ways: `external_id` now requires `^[A-Za-z0-9_-]+$` at the schema level (rejects `/`, `..`, etc. outright); the upload handler validates the camera exists *before* touching the filesystem; and the id is `os.path.basename()`-sanitized when building the path regardless, as defense in depth. Low real-world severity as found (both the create and upload endpoints already require the `admin` role), but input should never be trusted for a filesystem path regardless of who's allowed to send it.
- **Secrets themselves check out clean**: no hardcoded credentials anywhere in source (audited via grep across every service), `.env` is gitignored, dev-only secrets are clearly labeled as such, JWT decode pins its algorithm explicitly (no algorithm-confusion risk), passwords are bcrypt-hashed via `passlib`, and refresh tokens are single-use (revoked and reissued together on every refresh).
- **Noted, not changed**: no CORS middleware exists anywhere yet. Not a vulnerability in itself (a browser blocks cross-origin requests by default without it -- the absence is the safe default, not a hole), but it's a real gap for actually connecting a frontend dev server on a different origin; flagged for whoever wires that up rather than guessed at here.

**Load testing complete** -- full report at [`docs/load-test-report.md`](docs/load-test-report.md), reusable scripts in [`load-tests/`](load-tests/). The SAS gives no fixed numeric SLA for §11 ("N synthetic camera streams to validate the scaling assumptions" is the whole ask), so this defines its own methodology against the two claims the SAS actually makes:

- **API-facing services under concurrent load**: 15 virtual users continuously polling `dashboard/stats`/`cameras`/`events`/`alerts` through the real nginx gateway for 20s -- **0% errors**, 19.5 req/s sustained, p50 14.7ms / p95 160.9ms.
- **Multi-camera backpressure/graceful-degradation**: 5 concurrent camera pipelines (the existing one + 4 synthetic, reusing the session's test videos) sharing the one CPU-only `detection-service` instance. Ingestion held its normal ~3-4 fps/camera throughout (unaffected by the other pipelines); detection fell to ~27-33% of that under contention -- **exactly** the documented "frame skipping... rather than crashing" behavior, confirmed via the new `ingestion_frames_published_total`/`detection_frames_processed_total` Prometheus counters and each stream's Redis consumer-group lag (`cam:{id}:frames` sat pinned at its 200-entry cap; `cam:{id}:detections` downstream stayed at zero lag, proving the bottleneck doesn't cascade past Detection). Zero errors, zero crashes, all 14 containers stayed healthy throughout. Test cameras and their data were fully cleaned up afterward -- confirmed the dashboard's real counts were unaffected.

**CI pipeline complete** -- `.github/workflows/ci.yml` runs a 10-job matrix (every service + `ibvap_common`) on every push/PR to `main`, each job installing that package's own dependencies (plus the shared local `ibvap_common` lib, which `pip` needs installed explicitly first since it's a `uv`-style local path dependency plain `pip` doesn't resolve on its own) and running its full test suite. Every job's exact steps were run locally against a bare `python:3.12-slim` container before this was ever pushed, so there'd be no surprises -- and then verified for real: **all 10 jobs green on GitHub Actions** after the first push.

Deliberately scoped **out** of this pass: lint/type-check enforcement (`ruff`, `mypy --strict`, per Implementation Guide §3). This codebase was never developed against a project-specific lint config, and a bare default `ruff` ruleset against it produces mostly false-positive noise, not real signal -- 520 "violations," but 277 are an irrelevant shebang check and 109 are FastAPI's own standard `Depends(...)` idiom being flagged. Writing a real, tailored lint config (deciding which rules actually apply, allow-listing FastAPI's own patterns, etc.) is legitimate follow-up work, not something to invent inline here just to tick a box -- the Implementation Guide's own "Definition of Done" (§10) already defines this milestone's bar as "unit + integration tests green in CI," which this delivers.

Repo is live on GitHub (private) with this exact history -- `git init` was run mid-session specifically to enable this.

What's left beyond M10: Phase 2 capabilities only (re-ID, ANPR, richer zone editor UI, fire/smoke/tamper/animal detection) -- each additive on top of what's here, per the SAS's own §14 extensibility design, not a rework of anything already built.
