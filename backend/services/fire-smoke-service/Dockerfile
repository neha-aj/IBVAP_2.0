FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libgl1/libglib2.0-0: OpenCV (headless) needs these, same as detection-service.
# ultralytics/torch: doc11 §4's originally-missing fine-tuned YOLOv8-on-D-Fire
# weights now exist (see models/README.md) -- app/inference/yolo_scorer.py
# is the trained-model path, used when USE_TRAINED_FIRE_SMOKE_MODEL=true.
# The classical color/texture heuristic (heuristics.py) stays as the
# always-available default/fallback either way.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY libs/ibvap_common /srv/libs/ibvap_common
RUN pip install --no-cache-dir /srv/libs/ibvap_common

COPY services/fire-smoke-service/pyproject.toml /srv/pyproject.toml
COPY services/fire-smoke-service/app /srv/app

# Same CPU-only torch install as detection-service's own Dockerfile (see
# its comment for why: avoids pulling the much larger CUDA build, and
# ultralytics still auto-detects a GPU at runtime if one's ever attached).
RUN pip install --no-cache-dir --timeout 120 --retries 5 torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --timeout 120 --retries 5 \
    fastapi>=0.111 "uvicorn[standard]>=0.30" redis>=5.0 httpx>=0.27 numpy>=1.26 \
    "opencv-python-headless>=4.10,<5" pydantic>=2.7 pydantic-settings>=2.3 \
    structlog>=24.1 prometheus-client>=0.20 ultralytics>=8.2

# ultralytics pulls in plain `opencv-python` (GUI build) as its own
# transitive dependency -- a different PyPI distribution than
# opencv-python-headless above, but both install into the same on-disk
# `cv2` package, so whichever installs last silently corrupts the other's
# files (confirmed live-breaking anpr-service's cv2.CascadeClassifier the
# same way). Force headless back in as the last word, preventatively, even
# though nothing here has hit a broken attribute yet.
RUN pip install --no-cache-dir --force-reinstall --no-deps "opencv-python-headless>=4.10,<5"

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
