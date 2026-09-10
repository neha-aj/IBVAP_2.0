FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) needs these, same as detection-service.
# No torch/ultralytics here -- doc11 §4's primary (fine-tuned YOLOv8 on
# D-Fire) and fallback (a pretrained fire-detection checkpoint) both need
# fire/smoke-labeled weights that don't exist for this deployment, and
# unlike Re-ID's ResNet-50 fallback there's no generic pretrained
# classifier that transfers to "is this fire" the way ImageNet features
# transfer to "is this the same person" -- so this service uses a classical
# color/texture heuristic instead (app/inference/heuristics.py's own
# docstring covers the reasoning and its real limitations).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/fire-smoke-service/pyproject.toml /srv/pyproject.toml
COPY services/fire-smoke-service/app /srv/app

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 numpy>=1.26 \
    "opencv-python-headless>=4.10,<5" pydantic>=2.7 pydantic-settings>=2.3 \
    structlog>=24.1 prometheus-client>=0.20

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
