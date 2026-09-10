FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) needs these -- Phase 2 M23's
# recording-clip producer is this service's first use of OpenCV (assembling
# captured post-roll frames into an MP4), same runtime deps every other
# OpenCV-using service in this project already installs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/event-alert-service/pyproject.toml /srv/pyproject.toml
COPY services/event-alert-service/app /srv/app
COPY services/event-alert-service/alembic /srv/alembic
COPY services/event-alert-service/alembic.ini /srv/alembic.ini

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 alembic>=1.13 redis>=5.0 httpx>=0.27 pydantic>=2.7 \
    pydantic-settings>=2.3 structlog>=24.1 prometheus-client>=0.20 \
    numpy>=1.26 "opencv-python-headless>=4.10,<5"

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
