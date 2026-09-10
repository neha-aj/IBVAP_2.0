import pytest

from app.inference.fusion_merger import FusionMerger, FusionSettings, ModalityFeed, merge_detections
from app.schemas.detection import BoundingBox, Detection


def _detection(
    *, id: str = "d1", camera_id: str = "CAM-01", type: str = "person", confidence: float,
    x: float = 10.0, y: float = 10.0, width: float = 10.0, height: float = 10.0,
) -> Detection:
    return Detection(
        id=id, camera_id=camera_id, type=type, confidence=confidence,
        bbox=BoundingBox(x=x, y=y, width=width, height=height),
    )


def _settings(**overrides) -> FusionSettings:
    return FusionSettings(**overrides)


def test_high_confidence_rgb_detection_passes_through_unconsulted() -> None:
    """§6 step 1/2: an RGB detection at or above low_conf_threshold is
    trusted outright -- thermal isn't even checked, so fusion_score stays
    None even when a thermal box happens to overlap it."""
    rgb = [_detection(confidence=0.9)]
    thermal = [_detection(id="t1", confidence=0.99, type="animal")]  # would overlap and disagree on type

    merged = merge_detections(rgb, thermal, _settings())

    assert len(merged) == 2  # the trusted RGB one, plus the unmatched thermal one
    rgb_result = next(d for d in merged if d.id == "d1")
    assert rgb_result.confidence == 0.9
    assert rgb_result.fusion_score is None
    assert rgb_result.type == "person"


def test_low_confidence_rgb_boosted_by_overlapping_thermal_detection() -> None:
    """§6 step 2: low-confidence RGB + overlapping thermal -> boosted
    confidence, recorded fusion_score, not suppressed."""
    rgb = [_detection(confidence=0.30, x=10, y=10, width=10, height=10)]
    thermal = [_detection(id="t1", confidence=0.6, x=12, y=12, width=10, height=10, type="person")]

    merged = merge_detections(rgb, thermal, _settings(confidence_boost=0.25, min_iou=0.30))

    assert len(merged) == 1  # the thermal counterpart is consumed into the boosted result, not duplicated
    result = merged[0]
    assert result.confidence == pytest.approx(0.55)  # 0.30 + 0.25
    assert result.fusion_score is not None and result.fusion_score > 0.30


def test_boosted_detection_type_defers_to_higher_confidence_modality() -> None:
    """§6 step 3: type classification defers to whichever modality's box
    ends up with the higher confidence."""
    rgb = [_detection(confidence=0.30, type="vehicle", x=10, y=10, width=10, height=10)]
    # Thermal's own confidence (0.9) beats the RGB detection's *boosted*
    # confidence (0.55) -- thermal's type should win.
    thermal = [_detection(id="t1", confidence=0.9, type="person", x=12, y=12, width=10, height=10)]

    merged = merge_detections(rgb, thermal, _settings(confidence_boost=0.25, min_iou=0.30))

    assert merged[0].type == "person"


def test_low_confidence_rgb_with_no_thermal_agreement_is_suppressed() -> None:
    """§6 step 2: no thermal overlap and confidence below suppress_threshold
    -- dropped as a likely shadow/glare/debris false positive."""
    rgb = [_detection(confidence=0.10)]
    thermal: list[Detection] = []

    merged = merge_detections(rgb, thermal, _settings(suppress_threshold=0.25))

    assert merged == []


def test_ambiguous_confidence_band_with_no_thermal_agreement_is_kept() -> None:
    """Between suppress_threshold and low_conf_threshold, no thermal
    overlap either way -- not confident enough to trust blindly, not low
    enough to safely drop. Kept as-is rather than guessed at."""
    rgb = [_detection(confidence=0.30)]
    thermal: list[Detection] = []

    merged = merge_detections(rgb, thermal, _settings(suppress_threshold=0.25, low_conf_threshold=0.35))

    assert len(merged) == 1
    assert merged[0].confidence == 0.30
    assert merged[0].fusion_score is None


def test_thermal_only_detection_passes_through_unchanged() -> None:
    """§6 step 3: a thermal detection with no RGB counterpart (e.g. a
    fully dark scene) passes through as a normal detection."""
    rgb: list[Detection] = []
    thermal = [_detection(id="t1", confidence=0.7, type="person")]

    merged = merge_detections(rgb, thermal, _settings())

    assert len(merged) == 1
    assert merged[0].id == "t1"
    assert merged[0].fusion_score is None


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Detection]]] = []

    async def publish(self, camera_id: str, detections: list[Detection], *, loop_generation: int = 0) -> None:
        self.calls.append((camera_id, detections))


@pytest.mark.asyncio
async def test_fusion_merger_publishes_solo_when_no_partner_within_tolerance() -> None:
    publisher = _RecordingPublisher()
    merger = FusionMerger(camera_id="CAM-DUAL-01", publisher=publisher, settings=_settings())

    await merger.submit(modality="rgb", detections=[_detection(confidence=0.9)], loop_generation=0)

    assert len(publisher.calls) == 1
    camera_id, detections = publisher.calls[0]
    assert camera_id == "CAM-DUAL-01"
    assert len(detections) == 1


@pytest.mark.asyncio
async def test_fusion_merger_merges_when_both_modalities_submit_promptly() -> None:
    publisher = _RecordingPublisher()
    merger = FusionMerger(camera_id="CAM-DUAL-01", publisher=publisher, settings=_settings())

    await merger.submit(
        modality="rgb", detections=[_detection(confidence=0.30, x=10, y=10, width=10, height=10)], loop_generation=0
    )
    await merger.submit(
        modality="thermal",
        detections=[_detection(id="t1", confidence=0.6, x=12, y=12, width=10, height=10)],
        loop_generation=0,
    )

    assert len(publisher.calls) == 2  # the solo RGB publish, then the merged publish
    _, second_batch = publisher.calls[1]
    assert len(second_batch) == 1
    assert second_batch[0].fusion_score is not None


@pytest.mark.asyncio
async def test_modality_feed_forwards_into_the_shared_merger() -> None:
    publisher = _RecordingPublisher()
    merger = FusionMerger(camera_id="CAM-DUAL-01", publisher=publisher, settings=_settings())
    feed = ModalityFeed(merger, modality="rgb")

    await feed.publish("CAM-DUAL-01", [_detection(confidence=0.9)], loop_generation=3)

    assert len(publisher.calls) == 1
