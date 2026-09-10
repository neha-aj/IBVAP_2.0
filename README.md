# IBVAP+Thermal

Intelligent Border Video Analytics Platform -- a full-stack surveillance/video-analytics system: a microservices backend (detection, tracking, ANPR, PPE, fire/smoke, tamper, person/vehicle re-identification, rules-based alerting) plus a React frontend (live surveillance, alerts, events, analytics dashboards).

This is the **thermal fusion + edge deployment** prototype (M11): dual RGB+thermal camera capture, cross-modal detection fusion, and an offline-capable edge deployment profile, layered on top of the same base platform as [`neha-aj/IBVAP`](https://github.com/neha-aj/IBVAP). See [`backend/services/detection-service/app/inference/fusion_merger.py`](backend/services/detection-service/app/inference/fusion_merger.py) for the fusion rule and [`backend/services/detection-service/app/inference/`](backend/services/detection-service/app/inference/) for the edge outbox/sync/local-rules pieces.

This repo is a combined, point-in-time snapshot of two actively-developed repos, published here as a single copy to share:

- **[`backend/`](backend/)** -- the microservices backend. See [`backend/README.md`](backend/README.md) for architecture, setup, and how to run the whole stack with `docker compose up`.
- **[`frontend/`](frontend/)** -- the React frontend. See [`frontend/README.md`](frontend/README.md) to run it against the backend.

Each folder is self-contained with its own dependencies and its own README -- start there.

## Running locally

Use `start.ps1` / `stop.ps1` in this folder (same pattern as the base IBVAP prototype) -- they bring up the backend Docker stack under its own Compose project name (`ibvap-thermal`, set via `backend/.env`) and the frontend dev server, without disturbing a sibling IBVAP checkout.
