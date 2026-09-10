FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) needs these, same as detection-service.
# tesseract-ocr: the OCR engine itself -- pytesseract is just a thin wrapper
# around this binary, per doc11's own "Tesseract... zero-dependency and
# CPU-light" fallback recommendation (chosen here over PaddleOCR/EasyOCR
# specifically to avoid pulling in a second deep-learning framework beyond
# detection-service's already-established torch/ultralytics one).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/anpr-service/pyproject.toml /srv/pyproject.toml
COPY services/anpr-service/app /srv/app
COPY services/anpr-service/alembic /srv/alembic
COPY services/anpr-service/alembic.ini /srv/alembic.ini

RUN pip install --no-cache-dir \
    fastapi>=0.111 "uvicorn[standard]>=0.30" "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 alembic>=1.13 redis>=5.0 httpx>=0.27 numpy>=1.26 \
    "opencv-python-headless>=4.10,<5" pytesseract>=0.3.10 pydantic>=2.7 \
    pydantic-settings>=2.3 structlog>=24.1 prometheus-client>=0.20

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
