from app.inference.ocr import is_valid_plate_format, parse_ocr_result

_PATTERN = r"^[A-Z0-9]{5,10}$"


def test_parse_ocr_result_combines_words_and_uppercases() -> None:
    result = parse_ocr_result(["ab", "123", "cd"], [80.0, 90.0, 85.0], min_confidence=40.0)
    assert result == ("AB123CD", 85.0)


def test_parse_ocr_result_strips_non_alphanumeric() -> None:
    result = parse_ocr_result(["AB-123"], [90.0], min_confidence=40.0)
    assert result == ("AB123", 90.0)


def test_parse_ocr_result_none_when_no_text() -> None:
    assert parse_ocr_result([], [], min_confidence=40.0) is None


def test_parse_ocr_result_none_when_below_confidence_threshold() -> None:
    assert parse_ocr_result(["AB123"], [10.0], min_confidence=40.0) is None


def test_parse_ocr_result_none_when_only_punctuation() -> None:
    assert parse_ocr_result(["--"], [90.0], min_confidence=40.0) is None


def test_is_valid_plate_format_accepts_alphanumeric_in_range() -> None:
    assert is_valid_plate_format("AB123CD", _PATTERN) is True


def test_is_valid_plate_format_rejects_too_short() -> None:
    assert is_valid_plate_format("AB1", _PATTERN) is False


def test_is_valid_plate_format_rejects_lowercase() -> None:
    assert is_valid_plate_format("ab123cd", _PATTERN) is False
