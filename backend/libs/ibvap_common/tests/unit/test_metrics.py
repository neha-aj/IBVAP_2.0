from fastapi import FastAPI
from fastapi.testclient import TestClient

from ibvap_common.metrics import install_metrics


def _app() -> FastAPI:
    app = FastAPI()
    install_metrics(app, "test-service")

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    return app


def test_metrics_endpoint_returns_prometheus_text_format() -> None:
    client = TestClient(_app())

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_request_count_increments_after_a_call() -> None:
    client = TestClient(_app())
    client.get("/ping")

    body = client.get("/metrics").text

    assert 'http_requests_total{method="GET",path="/ping",service="test-service",status="200"}' in body


def test_request_latency_histogram_is_recorded() -> None:
    client = TestClient(_app())
    client.get("/ping")

    body = client.get("/metrics").text

    assert 'http_request_duration_seconds_count{method="GET",path="/ping",service="test-service"}' in body
