FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# `supervision` pulls in opencv-python (for its annotation utilities, unused
# here) which needs these shared libs at import time even in headless use.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/tracking-service/pyproject.toml /srv/pyproject.toml
COPY services/tracking-service/app /srv/app

# No torch/GPU here -- ByteTrack (via `supervision`) is Kalman filtering +
# Hungarian matching, plain numpy/scipy, CPU-only by nature.
# supervision pinned <0.31: sv.ByteTrack is deprecated (removal slated for
# 0.31.0, no replacement named yet) -- see pyproject.toml for detail.
RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 \
    numpy>=1.26 pydantic>=2.7 pydantic-settings>=2.3 structlog>=24.1 \
    prometheus-client>=0.20 "supervision>=0.24,<0.31"

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
