FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) and MediaPipe both need these,
# same as detection-service/fire-smoke-service. libgles2/libegl1: MediaPipe
# Tasks' native library (`mediapipe_c_bindings`) dlopens libGLESv2.so.2 at
# import time even for CPU-only inference -- confirmed by hand, the service
# crashes on startup with `OSError: libGLESv2.so.2: cannot open shared
# object file` without these; libgl1 alone (enough for OpenCV) does not
# provide it. curl: fetches the MediaPipe pose-landmarker model bundle
# below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgles2 libegl1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/pose-service/pyproject.toml /srv/pyproject.toml
COPY services/pose-service/app /srv/app

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 numpy>=1.26 \
    "opencv-python-headless>=4.10,<5" "mediapipe>=0.10,<0.11" pydantic>=2.7 \
    pydantic-settings>=2.3 structlog>=24.1 prometheus-client>=0.20

# MediaPipe's official pretrained "pose_landmarker_lite" Tasks-API model
# bundle (CPU, BlazePose-based, multi-person via `num_poses` -- see
# app/inference/pose_classifier.py's own docstring). "lite" variant chosen
# over "full"/"heavy": this service runs one independent detection per
# sampled camera per model-instance-per-camera (see
# app/streaming/reconcile_manager.py's own docstring for why one model
# instance per camera, not one shared instance), so keeping each instance's
# CPU/memory footprint small matters more here than in a single-stream
# demo. Swappable to "pose_landmarker_full.task"/"pose_landmarker_heavy.task"
# from the same Google-hosted bucket for higher accuracy at higher cost if
# this deployment's hardware allows it later.
RUN mkdir -p /srv/models && \
    curl -fsSL -o /srv/models/pose_landmarker.task \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /srv/models
USER appuser

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
