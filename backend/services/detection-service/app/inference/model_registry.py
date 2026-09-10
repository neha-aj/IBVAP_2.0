"""Selects the inference backend once at startup (SAS §5.2, §9: "GPU if
available, ONNX Runtime CPU fallback"). `inference_backend`:

- "onnx": force the ONNX Runtime backend (requires `onnx_model_path` to exist
  and the optional `onnx` dependency group installed).
- "torch": force the Ultralytics/torch backend.
- "auto" (default): use ONNX Runtime if a model file is present at
  `onnx_model_path` (the lean, no-torch CPU path), otherwise fall back to
  Ultralytics, which downloads/loads `model_path` itself and picks CUDA
  automatically when available.
"""

from __future__ import annotations

import os

from ibvap_common.logging import get_logger

from app.core.config import Settings
from app.inference.base import InferenceEngine

logger = get_logger(__name__)


def build_engine(settings: Settings) -> InferenceEngine:
    backend = settings.inference_backend
    onnx_available = os.path.exists(settings.onnx_model_path)

    use_onnx = backend == "onnx" or (backend == "auto" and onnx_available)
    if use_onnx:
        from app.inference.onnx_runner import OnnxRunner

        logger.info("inference_backend_selected", backend="onnx", model=settings.onnx_model_path)
        return OnnxRunner(
            model_path=settings.onnx_model_path,
            confidence_threshold=settings.confidence_threshold,
            input_size=settings.onnx_input_size,
        )

    from app.inference.yolo_runner import YoloRunner

    logger.info("inference_backend_selected", backend="torch", model=settings.model_path)
    return YoloRunner(
        model_path=settings.model_path, confidence_threshold=settings.confidence_threshold
    )
