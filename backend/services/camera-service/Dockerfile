FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/camera-service/pyproject.toml /srv/pyproject.toml
COPY services/camera-service/app /srv/app
COPY services/camera-service/alembic /srv/alembic
COPY services/camera-service/alembic.ini /srv/alembic.ini

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 alembic>=1.13 pydantic>=2.7 pydantic-settings>=2.3 \
    "python-multipart>=0.0.9" redis>=5.0 structlog>=24.1 httpx>=0.27

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
