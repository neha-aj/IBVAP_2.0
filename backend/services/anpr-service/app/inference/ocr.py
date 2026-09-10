"""OCR + plate-format validation. `parse_ocr_result`/`is_valid_plate_format`
are pure functions (testable without the Tesseract binary installed);
`read_plate_text` is the thin wrapper that actually calls it, per doc11 §1's
Tesseract fallback (chosen over PaddleOCR/EasyOCR to avoid a second deep-
learning framework dependency -- see Dockerfile's own comment)."""

from __future__ import annotations

import re

import numpy as np
import pytesseract


def parse_ocr_result(
    raw_texts: list[str], raw_confidences: list[float], *, min_confidence: float,
) -> tuple[str, float] | None:
    """`raw_texts`/`raw_confidences` are Tesseract's own per-word output
    (`image_to_data`'s "text"/"conf" columns, already filtered to non-empty
    words by the caller). Returns (plate_text, avg_confidence) or None if
    nothing usable was read or confidence falls below threshold."""
    if not raw_texts:
        return None
    combined = re.sub(r"[^A-Z0-9]", "", "".join(raw_texts).upper())
    if not combined:
        return None
    avg_confidence = sum(raw_confidences) / len(raw_confidences)
    if avg_confidence < min_confidence:
        return None
    return combined, avg_confidence


def is_valid_plate_format(plate_text: str, pattern: str) -> bool:
    """doc09 §2.1: "regex/format validation against configurable regional
    plate formats... avoids storing OCR garbage as a 'read'"."""
    return bool(re.match(pattern, plate_text))


def read_plate_text(gray_crop: np.ndarray, *, min_confidence: float) -> tuple[str, float] | None:
    if gray_crop.size == 0:
        return None
    data = pytesseract.image_to_data(gray_crop, config="--psm 8", output_type=pytesseract.Output.DICT)
    texts: list[str] = []
    confidences: list[float] = []
    for text, conf in zip(data.get("text", []), data.get("conf", []), strict=False):
        text = text.strip()
        if not text:
            continue
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            continue
        if confidence < 0:  # Tesseract uses -1 for "no confidence value"
            continue
        texts.append(text)
        confidences.append(confidence)
    return parse_ocr_result(texts, confidences, min_confidence=min_confidence)
