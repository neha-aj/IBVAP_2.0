FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Shared internal library first (installed as a normal dependency; IG §3).
COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/auth-service/pyproject.toml /srv/pyproject.toml
COPY services/auth-service/app /srv/app
COPY services/auth-service/alembic /srv/alembic
COPY services/auth-service/alembic.ini /srv/alembic.ini

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 alembic>=1.13 pydantic>=2.7 pydantic-settings>=2.3 \
    "passlib[bcrypt]>=1.7" "bcrypt<4.1" pyjwt>=2.8 structlog>=24.1

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Apply migrations then start the API -- keeps `docker compose up` self-sufficient.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
