FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/realtime-gateway/pyproject.toml /srv/pyproject.toml
COPY services/realtime-gateway/app /srv/app

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 pydantic>=2.7 \
    pydantic-settings>=2.3 structlog>=24.1

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
