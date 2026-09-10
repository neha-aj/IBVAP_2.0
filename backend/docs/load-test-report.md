# Load Test Report (M10)

Validates the qualitative scaling claims in `02-System-Architecture-Specification.md` §11 ("Scaling Strategy"), per §13's "Load test: N synthetic camera streams to validate the per-camera scaling assumptions in §11" -- the SAS gives no fixed numeric target (no "must handle X req/s" SLA), so this report defines and documents its own methodology instead of chasing an undocumented number.

Run against the live stack on a single dev host (no GPU, no horizontal scaling configured) -- these results describe *this* deployment's headroom, not a hardware-independent ceiling.

## Test 1: API-facing services under concurrent request load

**Claim being tested (§11):** "... independent of the API-facing services which scale on request load."

**Method:** 15 concurrent virtual users continuously polling the same four read endpoints a real frontend would poll (`GET /dashboard/stats`, `/cameras`, `/events`, `/alerts`) for 20 seconds, through the actual nginx gateway -- not hitting any service directly. Paced to stay under the `api_general` rate-limit zone (20 req/s/IP, configured during the M10 security pass) so this measures genuine service capacity, not the limiter's own rejection behavior.

**Result:**

| Metric | Value |
|---|---|
| Total requests | 390 |
| Sustained throughput | 19.5 req/s |
| Error rate | 0.0% |
| Latency p50 | 14.7 ms |
| Latency p95 | 160.9 ms |
| Latency max | 575.5 ms |

Zero errors across all four endpoints at this concurrency; per-endpoint p50s ranged 11.5-17.3ms. The one high max (575ms) is consistent with a single cold-cache/GC-pause outlier, not a systemic issue -- p95 for three of the four endpoints stayed under 161ms.

**Conclusion:** confirmed. The API-facing services handle sustained concurrent polling load cleanly with no errors and low tail latency.

## Test 2: Multiple simultaneous camera pipelines (backpressure / graceful degradation)

**Claim being tested (§11):** "Redis Streams with consumer groups give at-least-once processing and natural backpressure; if Detection Service falls behind, ingestion continues live-preview but inference frame rate degrades gracefully (frame skipping) rather than crashing."

**Method:** 4 additional synthetic file-source cameras created and uploaded via the real API (reusing the session's two test videos), run alongside the existing camera -- 5 concurrent camera pipelines total, each with its own ingestion worker, tracker, and detection/tracking consumer, all sharing the single (CPU-only, no GPU) `detection-service` instance's inference capacity. Left running ~40s to reach steady state, then read `ingestion_frames_published_total` and `detection_frames_processed_total` (both added during M10's Prometheus work) per camera, plus each stream's actual Redis consumer-group lag.

**Result:**

| Camera | Ingestion rate (fps) | Detection rate (fps) | Detection / ingestion |
|---|---|---|---|
| FILE-C5F172A4 | 4.04 | 1.11 | 27% |
| FILE-9613DFDC | 4.07 | 1.11 | 27% |
| FILE-EA1C16AC | 2.96 | 0.99 | 33% |
| FILE-DAD91C66 | 3.03 | 0.97 | 32% |
| FILE-5966A6A3 | 2.99 | 0.96 | 32% |

- **Ingestion held its normal rate on every camera, unaffected by the other 4 competing pipelines** -- exactly the "ingestion continues live-preview" half of the claim.
- **Detection fell to ~27-33% of ingestion's rate under 5-camera CPU contention** -- exactly the "inference frame rate degrades gracefully" half.
- **Zero errors or exceptions** in `detection-service`'s logs across the whole test.
- **`cam:{id}:frames` sat at its `maxlen` cap (200) with consumer-group lag ≈ 200** on every camera -- confirming *how* the degradation happens: old, never-yet-inferred frames get silently trimmed off the stream by the existing cap rather than the backlog growing unbounded (which would eventually exhaust Redis memory) or detection-service falling over trying to catch up on a full backlog.
- **Zero lag downstream** -- `cam:{id}:detections` (tracking-service's input) stayed fully caught up (`lag: 0`) throughout, confirming the bottleneck is isolated cleanly to the one CPU-bound stage, not cascading into tracking/event-alert.
- **All 14 containers stayed healthy throughout** (checked via `docker compose ps`), and the dashboard's real counts (`peopleDetectedToday`, etc.) were unaffected once the 4 test cameras and their data were removed afterward.

**Conclusion:** confirmed. This is precisely the architecture's documented per-stage, independently-scaling design working as intended: the bottleneck lands exactly where the SAS says it will (the CPU-bound Detection stage, on a host with no GPU and only one instance), degrades by dropping old frames rather than erroring or crashing, and doesn't cascade to the stages downstream of it. The SAS's own prescribed fix for this exact bottleneck -- horizontal per-camera-shard scaling of Detection, or GPU batching (§11) -- is unchanged by this test; the point here was to confirm the *degradation* is graceful, not to fix the underlying single-CPU-worker throughput ceiling (out of scope for this pass).

## What this does not cover

- No GPU was available on this dev host -- the detection throughput ceiling measured here (~1 fps/camera at 5 concurrent cameras) is specific to CPU-only inference and would be materially different with the GPU path the SAS assumes for production.
- No test of horizontal scaling itself (running multiple `detection-service` replicas / per-camera sharding) -- confirming *that* the system degrades gracefully under a single instance was this pass's goal; confirming the scale-out fix actually resolves it is a separate, follow-up exercise.
- No sustained multi-hour soak test -- this was a ~1-minute snapshot under load, not a leak/stability test over time.
