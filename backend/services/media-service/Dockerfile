FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/media-service/pyproject.toml /srv/pyproject.toml
COPY services/media-service/app /srv/app
COPY services/media-service/alembic /srv/alembic
COPY services/media-service/alembic.ini /srv/alembic.ini

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 alembic>=1.13 "python-multipart>=0.0.9" pydantic>=2.7 \
    pydantic-settings>=2.3 structlog>=24.1

RUN mkdir -p /data/media && useradd --create-home --uid 1000 appuser && chown -R appuser /data/media
USER appuser

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
