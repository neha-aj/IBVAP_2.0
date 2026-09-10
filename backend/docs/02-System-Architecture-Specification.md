# IBVAP — System Architecture Specification (SAS)

**Status:** Single source of truth for backend/AI/infra architecture, Phase 1 onward. Optimized to extend to Phase 2+ (re-ID, ANPR, intrusion/loitering/fire/tamper/animal detection) without structural rework.

---

## 1. Architectural Style

Microservice architecture, async, message/event-driven for the video pipeline, REST + WebSocket for client-facing APIs. No service imports another service's code; all cross-service interaction is over the network (HTTP, WebSocket, or Redis Streams/Pub-Sub). Each service owns its own data (database-per-service where practical; Phase 1 uses a shared PostgreSQL instance with **schema-per-service** to reduce operational overhead while preserving logical isolation — see §6).

## 2. High-Level Diagram

```
                                   ┌─────────────────────────┐
                                   │   NGINX (API Gateway +   │
                                   │   reverse proxy + TLS)   │
                                   └────────────┬─────────────┘
                                                │
        ┌───────────────┬───────────────┬──────┴───────┬───────────────┬────────────────┐
        │               │               │              │               │                │
  ┌─────▼────┐   ┌──────▼─────┐  ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐  ┌───────▼───────┐
  │  Auth    │   │  Camera    │  │   Event/     │ │  Analytics │ │  Realtime   │  │   Media        │
  │ Service  │   │  Mgmt Svc  │  │   Alert Svc  │ │  Service   │ │  Gateway    │  │   Storage Svc  │
  └─────┬────┘   └──────┬─────┘  └──────┬──────┘ └─────┬──────┘ └──────┬──────┘  └───────┬───────┘
        │               │               │              │               │                 │
        └───────────────┴───────┬───────┴──────────────┴───────┬───────┴─────────────────┘
                                 │                               │
                          ┌──────▼───────┐               ┌───────▼────────┐
                          │  PostgreSQL   │               │     Redis       │
                          │ (schema/svc)  │               │ (cache + streams│
                          └───────────────┘               │  + pub/sub)     │
                                                           └────────┬────────┘
                                                                    │
        ┌───────────────────────────────────────────────────────┴─────────────────────────────┐
        │                              Video / AI Pipeline (per camera)                          │
        │                                                                                         │
  ┌─────▼───────────┐   frames    ┌──────────────────┐  detections  ┌────────────────┐  tracks   │
  │ Stream Ingestion │────────────▶│ Detection Service │─────────────▶│ Tracking Service│──────────┤
  │ Service (FFmpeg/ │             │ (YOLO/Ultralytics/│              │  (ByteTrack)    │          │
  │ OpenCV, per-cam  │             │  ONNX Runtime)     │              │                 │          │
  │ worker)          │             └──────────────────┘              └────────┬────────┘          │
  └─────────┬────────┘                                                        │ tracked events      │
            │ raw frame + health                                              ▼                    │
            │                                                        ┌────────────────┐            │
            └───────────────────────────────────────────────────────▶│  Rule/Event     │           │
                                                                      │  Engine (part of│           │
                                                                      │  Event/Alert Svc)│          │
                                                                      └────────┬────────┘           │
                                                                               │                     │
                                                                    events/alerts + snapshot jobs    │
                                                                               ▼                     │
                                                                     Postgres + Media Storage Svc     │
        └─────────────────────────────────────────────────────────────────────────────────────────┘
```

## 3. Microservices — Responsibilities

| Service | Responsibility | Talks to |
|---|---|---|
| **API Gateway (NGINX)** | TLS termination, routing `/api/v1/*` to services, WebSocket upgrade proxying, rate limiting, static media serving (or delegates to Media Storage Svc) | All services |
| **Auth Service** | User accounts, JWT issue/refresh, RBAC (admin/operator/viewer), password hashing | Postgres (`auth` schema), Redis (refresh-token/blacklist cache) |
| **Camera Management Service** | Camera CRUD, camera health/status state machine, sector/zone management, settings (Settings page) | Postgres (`camera` schema), Redis (status cache), publishes `camera.status_changed` |
| **Stream Ingestion Service** | One worker/process-group per camera; connects RTSP/USB/IP source via OpenCV+FFmpeg, decodes frames, republishes frames to Redis Stream, emits heartbeats, produces live preview (MJPEG/HLS) for the "LIVE" view | Camera Mgmt Svc (camera config), Redis Streams, Media Storage (optional segment recording) |
| **Detection Service** | Consumes frames from Redis Stream, runs YOLO inference (batched where possible), emits normalized detections (`bbox` as % of frame, matching frontend contract) | Redis Streams (in: frames, out: detections) |
| **Tracking Service** | Consumes detections per camera, runs ByteTrack, assigns/maintains persistent `track_id`s across frames, emits tracked-object events (new track, updated track, lost track) | Redis Streams (in: detections, out: tracked_objects) |
| **Event/Alert Service** | Rule engine consuming tracked-object stream (zone intrusion, loitering time thresholds, restricted-zone entry, night movement, camera offline→"Connection Lost" alert, etc.), persists `events`/`alerts`, exposes REST for Events/Alerts pages, drives status transitions | Postgres (`events` schema), Redis Pub/Sub (out: `event.new`, `alert.new`, `alert.updated`), Media Storage Svc (request snapshot) |
| **Media Storage Service** | Persists snapshots/recordings to disk (local volume Phase 1; S3-compatible object storage ready for Phase 2), generates thumbnails, serves signed URLs | Postgres (`media` schema), filesystem/object store |
| **Analytics Service** | Scheduled/streaming aggregation (activity-by-hour, alerts-by-type, camera-uptime, events-by-camera, daily counters for Dashboard stat cards) | Postgres (reads across schemas via views), Redis (cached aggregates, short TTL) |
| **Realtime Gateway (WebSocket Service)** | Single WS endpoint for the frontend; subscribes to Redis Pub/Sub channels and fans out to connected clients, per-connection auth + topic subscription (e.g. subscribe to specific camera IDs) | Redis Pub/Sub, Auth Service (token validation) |
| **Notification Service** *(stub in Phase 1, real in later phase)* | Email/SMS/webhook fan-out for critical alerts | Event/Alert Svc (consumes `alert.new`) |

**Detection vs. Tracking as separate services:** kept separate (rather than one "AI service") specifically so that Phase 2 capabilities (re-ID, ANPR, face, fire/smoke, tamper, animal) can be added as additional consumers of the same frame/detection streams without touching Detection or Tracking — each new capability is its own microservice subscribing to the same Redis Streams.

## 4. Service Communication

- **Synchronous (REST)**: frontend ⇄ Gateway ⇄ service, for CRUD, queries, page loads.
- **Asynchronous (Redis Streams)**: high-throughput pipeline stages (frames → detections → tracks → rule engine) — chosen over a heavier broker (Kafka/RabbitMQ) for Phase 1 given single-node deployment target; the interface (`stream: cam:{id}:frames`, `stream: cam:{id}:detections`, `stream: cam:{id}:tracks`) is broker-agnostic enough to swap to Kafka in a later phase if scale demands it.
- **Pub/Sub (Redis)**: fan-out of "interesting" events to the Realtime Gateway (`alert.new`, `event.new`, `camera.status_changed`) — low-latency, at-most-once is acceptable since Postgres remains the durable source of truth (WS clients that miss a push get consistency back via REST refetch).
- **WebSocket**: Gateway ⇄ frontend, one connection per client, topic-based subscription (e.g. `{"subscribe": ["camera:BOP-01-CAM-01", "alerts", "events"]}`).

No service calls another service's internal DB directly. No service imports another service's Python package.

## 5. Detection / Tracking / Streaming / Snapshot Pipelines

### 5.1 Streaming pipeline
1. Camera Mgmt Svc stores connection config (RTSP URL / USB index / ONVIF details / uploaded file path / webcam device URI). Source types: `rtsp`, `ip`, `usb`, `file` (an uploaded video, treated as a virtual camera — looped or played once, operator-selectable), `webcam` (local capture device, e.g. laptop or USB webcam). This lets development and demos run entirely on inserted video files or a live webcam with zero real CCTV hardware, through the exact same pipeline as a production RTSP camera.
2. Ingestion worker (one asyncio task or process per camera, pool-managed) opens the source via OpenCV `VideoCapture` (FFmpeg backend) — the backend differs only in the capture module (`capture/rtsp.py`, `capture/file.py`, `capture/webcam.py`, etc.), all implementing the same `FrameSource` interface — reads frames at source FPS, downsamples to a configurable inference FPS (e.g. 5–10 fps) for the AI pipeline while keeping a higher-FPS path for live preview.
3. Live preview: ingestion worker also re-muxes to a low-latency MJPEG-over-HTTP or HLS segment output the frontend's future `<video>`/`<img>` element consumes directly (through NGINX).
4. Frame metadata + a reference (shared memory key or small JPEG-encoded payload) pushed to `cam:{id}:frames` Redis Stream.
5. Missed heartbeat (no frame in N seconds) → ingestion worker publishes `camera.status_changed → offline`; degraded FPS/resolution → `warning`.

### 5.2 Detection pipeline
1. Detection Service consumes `cam:{id}:frames`, decodes, runs YOLOv8 (Ultralytics) — GPU if available, ONNX Runtime CPU fallback.
2. Normalizes each box to percentage coordinates (`x,y,width,height` relative to frame) to match the exact frontend `DetectionOverlay` contract.
3. Publishes to `cam:{id}:detections` stream and a short-TTL Redis key for "current detections per camera" (powers `GET /cameras/{id}/detections/current` and the Surveillance page's live overlay).

### 5.3 Tracking pipeline
1. Tracking Service consumes `cam:{id}:detections` per camera, feeds ByteTrack, assigns/persists `track_id`.
2. Emits track lifecycle events (`track.started`, `track.updated`, `track.lost`) to `cam:{id}:tracks`.
3. Track lifetime, dwell time, and zone occupancy (evaluated against camera-configured polygons) are exactly the inputs the rule engine needs for loitering/intrusion detection in Phase 2.

### 5.4 Rule engine → events/alerts
1. Event/Alert Service consumes `cam:{id}:tracks` + `camera.status_changed`.
2. Rules (Phase 1): person/vehicle count thresholds, camera offline → alert, simple zone-crossing (if a zone polygon is configured) → "Fence Intrusion"/"Restricted Zone Entry", dwell time over threshold → "Loitering Detected".
3. Every rule firing writes an `events` row; rules flagged `requires_review=true` also write a linked `alerts` row (status=`active`).
4. Event/Alert Service requests a snapshot from Media Storage Svc (frame at trigger time) and links it (`events.snapshot_id`).
5. Publishes `event.new` / `alert.new` to Redis Pub/Sub → Realtime Gateway → frontend.

### 5.5 Snapshot pipeline
1. Triggered by: (a) event/alert creation, (b) manual "capture" API call, (c) periodic per-camera thumbnail refresh (for `CameraCard` future live thumbnails).
2. Detection/Ingestion service encodes the relevant frame as JPEG, sends to Media Storage Svc.
3. Media Storage Svc writes to disk (`/data/media/snapshots/{camera_id}/{yyyy-mm-dd}/{uuid}.jpg`) and inserts a `media` schema row; returns a stable URL served via NGINX (`/media/...`) with signed/expiring access if S3-backed later.

## 6. Database Architecture

Single PostgreSQL 16 instance, one schema per owning service (`auth`, `camera`, `events`, `media`, `analytics`). Cross-schema reads for analytics use read-only views; no service writes to another service's schema. Migrations managed independently per schema via Alembic (`alembic_version` table per schema). See Database Specification document for full DDL.

## 7. Storage Architecture

- **Structured data**: PostgreSQL.
- **Blob/media**: local Docker volume in Phase 1 (`/data/media`), abstracted behind a `StorageBackend` interface (Repository pattern) so swapping to S3/MinIO in a later phase touches only the Media Storage Service's backend implementation.
- **Hot cache / pipeline transport**: Redis (Streams + Pub/Sub + key-value cache for "current status"/"current detections").

## 8. Authentication & Authorization

- JWT access tokens (short-lived, ~15 min) + refresh tokens (Redis-backed, revocable), issued by Auth Service.
- API Gateway (or a shared FastAPI dependency library vendored into each service) validates the JWT signature/expiry on every request; role claim (`admin | operator | viewer`) enforced per-endpoint.
- WebSocket connections authenticate via token in the connection handshake (query param or `Sec-WebSocket-Protocol`), validated once at connect.
- Service-to-service calls (rare, mostly Gateway→service) use a shared internal network + optional mTLS in production; Redis is on an internal-only network, never exposed externally.

## 9. Deployment / Docker Architecture

Docker Compose for Phase 1 (single-host or small cluster); structured so migration to Kubernetes later is straightforward (each service already stateless + 12-factor).

```
docker-compose.yml
├── nginx                (reverse proxy, TLS, static/media serving)
├── postgres              (single instance, multiple schemas)
├── redis                 (streams + pubsub + cache)
├── auth-service
├── camera-service
├── ingestion-service     (scaled: one replica can host N camera workers, or 1 replica per camera at high camera counts)
├── detection-service     (GPU-enabled image variant available)
├── tracking-service
├── event-alert-service
├── media-service
├── analytics-service
├── realtime-gateway
└── (future) notification-service
```

Each service: its own Dockerfile, `/health` endpoint, non-root user, resource limits set in compose. GPU services (`detection-service`) use the NVIDIA container runtime; a CPU-only ONNX Runtime fallback image is provided for hosts without a GPU.

## 10. Logging & Monitoring

- Structured JSON logs (per service) to stdout → collected by Docker logging driver → (Phase 1) local file/ELK-ready; correlation ID propagated from Gateway through every downstream call and into pipeline messages for end-to-end tracing.
- `/health` (liveness) and `/ready` (readiness, checks DB/Redis connectivity) on every service.
- Prometheus metrics endpoint (`/metrics`) per service (request latency/count, pipeline FPS, queue depth, inference latency); Grafana dashboards for camera FPS/health, detection throughput, alert volume.
- Camera-level health (FPS, last-frame age, dropped-frame count) surfaced both as Prometheus metrics and as the `camera.status_changed` events driving the UI status dot.

## 11. Scaling Strategy

- **Horizontal**: Ingestion/Detection/Tracking services scale per-camera-shard (consistent hashing of camera_id → worker), independent of the API-facing services which scale on request load.
- **GPU batching**: Detection Service batches frames across cameras assigned to the same worker to maximize GPU utilization at high camera counts.
- **Backpressure**: Redis Streams with consumer groups give at-least-once processing and natural backpressure; if Detection Service falls behind, ingestion continues live-preview but inference frame rate degrades gracefully (frame skipping) rather than crashing.
- **Read scaling**: Analytics Service pre-aggregates into materialized views refreshed on a schedule so Dashboard/Analytics endpoints never scan raw `detections`/`events` tables directly at read time.

## 12. Security

- All external traffic TLS-terminated at NGINX; internal Docker network isolated from host.
- Secrets via environment variables / Docker secrets, never committed.
- Input validation via Pydantic models on every endpoint; SQLAlchemy parameterized queries only (no raw SQL string interpolation).
- RBAC enforced at endpoint level (e.g. only `admin`/`operator` can PATCH alert status; `viewer` is read-only).
- Rate limiting at NGINX for auth endpoints (brute-force mitigation).
- Media URLs are short-lived signed links once object storage is introduced (Phase 2+).

## 13. Testing Strategy

- Unit tests per service (pytest), mocking Redis/Postgres via `pytest-asyncio` + `testcontainers` or `docker-compose.test.yml`.
- Contract tests for every REST endpoint against the API Specification (schema validation both directions).
- Integration test: a synthetic camera (looped test video file as an RTSP/file source) run end-to-end through ingestion → detection → tracking → event/alert → WebSocket, asserting the frontend-facing payload shapes match §5 of the Frontend Analysis Report exactly.
- Load test: N synthetic camera streams to validate the per-camera scaling assumptions in §11 before onboarding real hardware.

## 14. Extensibility for Future Phases

Because Detection and Tracking publish to shared, camera-scoped Redis Streams, every future capability is additive:

| Future capability | Implementation shape |
|---|---|
| Person/Vehicle Re-ID | New service consuming `cam:{id}:tracks`, extracts embeddings, matches against a vector index (pgvector or a dedicated vector DB) |
| License Plate Recognition (ANPR) | New service consuming `cam:{id}:detections` filtered to `vehicle`, runs plate-detection + OCR sub-pipeline |
| Intrusion / Loitering | Already scaffolded in the Event/Alert Service rule engine (§5.4); Phase 2 adds richer polygon-zone editor in Camera Mgmt |
| Fire/Smoke Detection | New parallel detection model service consuming the same `cam:{id}:frames` stream |
| Camera Tamper Detection | New lightweight service comparing frame statistics over time from `cam:{id}:frames` |
| Animal Detection | Extra class in the same YOLO model or a second Detection Service instance with a different model/config |
| Face Detection | New service, same pattern as ANPR — never touches Detection/Tracking code |

No existing service's interface needs to change to add any of the above — each is a new consumer group on an existing stream, or a new topic published to the same Event/Alert Service ingestion contract.
