FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) needs these, same as detection-service.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/reid-service/pyproject.toml /srv/pyproject.toml
COPY services/reid-service/app /srv/app
COPY services/reid-service/alembic /srv/alembic
COPY services/reid-service/alembic.ini /srv/alembic.ini

# CPU-only torch wheels first (same reasoning as detection-service's own
# Dockerfile: avoids pulling ultralytics-style CUDA-inclusive wheels this
# service has no use for) -- torchvision's pretrained ResNet-50 is the
# embedding extractor itself (doc11 §2's "ResNet-50-based Re-ID embedding"
# fallback, used because no fine-tuned OSNet/TorchReID weights exist for
# this deployment; see app/inference/embedder.py's own docstring).
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 alembic>=1.13 pgvector>=0.3.0 redis>=5.0 httpx>=0.27 \
    "python-multipart>=0.0.9" numpy>=1.26 "opencv-python-headless>=4.10,<5" \
    "Pillow>=10.0" pydantic>=2.7 pydantic-settings>=2.3 structlog>=24.1 prometheus-client>=0.20

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
