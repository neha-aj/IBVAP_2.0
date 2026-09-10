"""HTTP load test against the IBVAP API gateway (M10).

Validates SAS §11's "API-facing services ... scale on request load" claim
by hitting the read-heavy endpoints a real frontend would poll continuously
(dashboard stats, camera list, events, alerts) with N concurrent virtual
users for a fixed duration, and reports latency percentiles + error rate.

Deliberately stays under nginx's `api_general` rate-limit zone (20 req/s/IP,
burst 40, from the M10 security pass) -- this measures genuine service
capacity, not the rate limiter's own rejection behavior.

Usage: run from anywhere that can reach the gateway.
  - From the host, with the stack up via `docker compose up`:
      BASE=http://localhost:8080 python load_test_http.py
  - From a container on the `ibvap-internal` network:
      BASE=http://nginx:80 python load_test_http.py
Update ADMIN_PASSWORD below (or pass via env) to match your `.env`.
See `docs/load-test-report.md` for the results this produced.
"""

import asyncio
import json
import os
import statistics
import sys
import time

import httpx

BASE = os.environ.get("BASE", "http://localhost:8080")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "DevAdminPass123!")
CONCURRENCY = 15
DURATION_SECONDS = 20
# Spread each virtual user's requests to stay under 20 req/s per source IP
# in aggregate (all virtual users share one client IP here).
REQUEST_INTERVAL_SECONDS = 15 / 20  # ~0.75s between one VU's requests


async def login(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{BASE}/api/v1/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()["accessToken"]


ENDPOINTS = [
    ("GET", "/api/v1/dashboard/stats"),
    ("GET", "/api/v1/cameras"),
    ("GET", "/api/v1/events"),
    ("GET", "/api/v1/alerts"),
]


async def worker(worker_id: int, token: str, results: list, stop_at: float) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        i = 0
        while time.monotonic() < stop_at:
            method, path = ENDPOINTS[i % len(ENDPOINTS)]
            i += 1
            start = time.perf_counter()
            try:
                resp = await client.request(method, f"{BASE}{path}", headers=headers)
                elapsed = time.perf_counter() - start
                results.append({"path": path, "status": resp.status_code, "elapsed": elapsed})
            except Exception as exc:
                elapsed = time.perf_counter() - start
                results.append({"path": path, "status": None, "elapsed": elapsed, "error": str(exc)})
            await asyncio.sleep(REQUEST_INTERVAL_SECONDS)


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token = await login(client)

    results: list = []
    stop_at = time.monotonic() + DURATION_SECONDS
    await asyncio.gather(*(worker(i, token, results, stop_at) for i in range(CONCURRENCY)))

    total = len(results)
    errors = [r for r in results if r["status"] is None or r["status"] >= 400]
    latencies = sorted(r["elapsed"] for r in results if r["status"] and r["status"] < 400)

    summary = {
        "concurrency": CONCURRENCY,
        "duration_seconds": DURATION_SECONDS,
        "total_requests": total,
        "throughput_rps": round(total / DURATION_SECONDS, 2),
        "error_count": len(errors),
        "error_rate_pct": round(100 * len(errors) / total, 2) if total else None,
        "latency_ms": {
            "min": round(min(latencies) * 1000, 1) if latencies else None,
            "p50": round(statistics.median(latencies) * 1000, 1) if latencies else None,
            "p95": round(latencies[int(len(latencies) * 0.95)] * 1000, 1) if latencies else None,
            "max": round(max(latencies) * 1000, 1) if latencies else None,
        },
        "by_endpoint": {},
    }
    for _method, path in ENDPOINTS:
        path_results = [r for r in results if r["path"] == path]
        path_latencies = sorted(r["elapsed"] for r in path_results if r["status"] and r["status"] < 400)
        path_errors = [r for r in path_results if r["status"] is None or r["status"] >= 400]
        summary["by_endpoint"][path] = {
            "count": len(path_results),
            "errors": len(path_errors),
            "p50_ms": round(statistics.median(path_latencies) * 1000, 1) if path_latencies else None,
            "p95_ms": round(path_latencies[int(len(path_latencies) * 0.95)] * 1000, 1) if path_latencies else None,
        }

    print(json.dumps(summary, indent=2))
    if errors[:5]:
        print("\nSample errors:", file=sys.stderr)
        for e in errors[:5]:
            print(e, file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
