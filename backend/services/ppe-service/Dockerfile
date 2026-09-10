FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) needs these, same as detection-
# service/fire-smoke-service. No torch/ultralytics here -- doc11 §5's
# primary (fine-tuned YOLOv8 on a PPE dataset) needs helmet/vest-labeled
# weights that don't exist for this deployment, so this service uses
# doc11 §5's own documented fallback instead: the generic person detector
# already upstream in the pipeline (detection-service) plus a classical
# color-region heuristic here (app/inference/ppe_heuristics.py's own
# docstring covers the reasoning and its real limitations).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/ppe-service/pyproject.toml /srv/pyproject.toml
COPY services/ppe-service/app /srv/app

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 numpy>=1.26 \
    "opencv-python-headless>=4.10,<5" pydantic>=2.7 pydantic-settings>=2.3 \
    structlog>=24.1 prometheus-client>=0.20

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
