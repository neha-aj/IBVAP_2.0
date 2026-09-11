FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# OpenCV (headless) needs these; ffmpeg is not required here since this
# service only JPEG-decodes frames already extracted by Ingestion (M3).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/detection-service/pyproject.toml /srv/pyproject.toml
COPY services/detection-service/app /srv/app

# Default (non-GPU) image: CPU-only torch wheels first, so `ultralytics`
# doesn't pull the much larger CUDA build (SAS §9 -- Dockerfile.gpu is the
# CUDA variant for hosts with an NVIDIA runtime). Ultralytics auto-detects
# CUDA at runtime regardless, so this same code path also works unmodified
# if this image is ever run with a GPU attached.
# --timeout/--retries: torch's CPU wheel is large enough that pip's default
# read timeout can trip on a slow/unstable connection mid-download (build-
# environment flakiness, not a real dependency problem) -- purely a build
# robustness setting, no effect on the installed package versions/behavior.
RUN pip install --no-cache-dir --timeout 120 --retries 5 torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --timeout 120 --retries 5 \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 \
    numpy>=1.26 opencv-python-headless>=4.10 pydantic>=2.7 pydantic-settings>=2.3 \
    structlog>=24.1 ultralytics>=8.2 prometheus-client>=0.20

RUN mkdir -p /srv/models && useradd --create-home --uid 1000 appuser && chown -R appuser /srv/models
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
