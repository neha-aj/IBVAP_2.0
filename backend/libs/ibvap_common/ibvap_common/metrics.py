"""Prometheus metrics (Implementation Guide M10: "Prometheus/Grafana").

Every service gets the same baseline HTTP metrics (request count, latency,
in-progress requests) for free via `install_metrics(app, service_name)`, plus
a `GET /metrics` endpoint for Prometheus to scrape. Pipeline services (whose
real work happens in background Redis Streams consumers, not HTTP handlers)
additionally define their own `Counter`/`Histogram` instances with
`prometheus_client` directly and increment them at the natural point in
their own code -- there's nothing generic to share for that part.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

_REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests handled",
    ["service", "method", "path", "status"],
)
_REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["service", "method", "path"],
)


def install_metrics(app: FastAPI, service_name: str) -> None:
    """Call once at service startup, alongside
    `install_correlation_id_middleware`/`install_error_handlers`."""

    @app.middleware("http")
    async def metrics_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # The raw path (not the route template) would blow up cardinality
        # for path-parameterized routes (`/cameras/{id}`, `/events/{id}`) --
        # `request.scope["route"].path` is the template FastAPI matched
        # against, available only after routing, so fall back to the raw
        # path only for genuinely unmatched routes (404s).
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        route = request.scope.get("route")
        path = route.path if route is not None else request.url.path
        _REQUEST_COUNT.labels(
            service=service_name, method=request.method, path=path, status=str(response.status_code)
        ).inc()
        _REQUEST_LATENCY.labels(service=service_name, method=request.method, path=path).observe(elapsed)
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
