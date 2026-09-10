"""M11 §6 thermal/RGB fusion merge -- isolated from `frame_consumer.py` so a
single-modality camera's inference/publish code path is completely
untouched. A 'dual' camera gets two `FrameConsumer`s (one per modality,
reading `cam:{id}:frames` and `cam:{id}:frames:thermal`), each pointed at a
`ModalityFeed` below instead of the real `DetectionPublisher` -- `ModalityFeed`
duck-types the same `.publish(camera_id, detections, loop_generation=...)`
shape `FrameConsumer` already calls unconditionally, so nothing there needs
to know fusion exists at all. Both feeds forward into one `FusionMerger`
per dual camera, which does the actual §6 merge and the one real publish.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.schemas.detection import BoundingBox, Detection
from app.streaming.detection_publisher import DetectionPublisher


@dataclass
class FusionSettings:
    frame_sync_tolerance_ms: float = 150.0
    low_conf_threshold: float = 0.35
    confidence_boost: float = 0.25
    suppress_threshold: float = 0.25
    min_iou: float = 0.30


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection-over-union of two percent-of-frame boxes -- both
    modalities' `Detection.bbox` are normalized against their own frame's
    width/height by `to_detections`, so they're directly comparable."""
    ax2, ay2 = a.x + a.width, a.y + a.height
    bx2, by2 = b.x + b.width, b.y + b.height
    inter_x1, inter_y1 = max(a.x, b.x), max(a.y, b.y)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_w, inter_h = max(0.0, inter_x2 - inter_x1), max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    union_area = a.width * a.height + b.width * b.height - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def merge_detections(
    rgb_detections: list[Detection], thermal_detections: list[Detection], settings: FusionSettings
) -> list[Detection]:
    """M11 §6 steps 2-3, run once per matched RGB/thermal frame pair.

    Every detection's fate is deliberately auditable (§6's own stated
    reason: a missed detection and a false alarm are both costly on a
    security system, and someone may need to know which modality drove a
    given alert) -- see the branch comments for exactly why each one
    survived, was boosted, or was dropped.
    """
    matched_thermal_indices: set[int] = set()
    merged: list[Detection] = []

    for det in rgb_detections:
        if det.confidence >= settings.low_conf_threshold:
            merged.append(det)  # already trusted -- no need to consult thermal at all
            continue

        best_iou = 0.0
        best_index: int | None = None
        for i, tdet in enumerate(thermal_detections):
            if i in matched_thermal_indices:
                continue
            iou = _iou(det.bbox, tdet.bbox)
            if iou > best_iou:
                best_iou = iou
                best_index = i

        if best_index is not None and best_iou > settings.min_iou:
            # Cross-modal agreement found -- boost, don't suppress, and
            # record the IoU as this detection's fusion_score.
            matched_thermal_indices.add(best_index)
            tdet = thermal_detections[best_index]
            boosted_confidence = min(1.0, det.confidence + settings.confidence_boost)
            # §6 step 3: "type classification defers to whichever modality
            # produced the higher-confidence box" -- applied here, at the
            # point where the two modalities actually agree on a region.
            winning_type = tdet.type if tdet.confidence > boosted_confidence else det.type
            merged.append(
                det.model_copy(
                    update={
                        "confidence": boosted_confidence,
                        "fusion_score": round(best_iou, 4),
                        "type": winning_type,
                    }
                )
            )
        elif det.confidence < settings.suppress_threshold:
            # No thermal agreement and confidence is low -- §6 step 2's
            # "likely shadow/glare/debris" case. Dropped, not published.
            continue
        else:
            # Between suppress_threshold and low_conf_threshold with no
            # thermal agreement either way -- not confident enough to
            # trust blindly, not low enough to safely drop. Kept as-is
            # rather than guessing.
            merged.append(det)

    # §6 step 3: thermal detections with no RGB counterpart (e.g. a fully
    # dark scene) pass through as normal detections. fusion_score stays
    # None -- there was nothing to compare them against.
    for i, tdet in enumerate(thermal_detections):
        if i not in matched_thermal_indices:
            merged.append(tdet)

    return merged


class FusionMerger:
    """One per 'dual' camera. Pairs the two modalities' detection batches
    by nearest arrival time (tolerance `settings.frame_sync_tolerance_ms`)
    and publishes the merged result.

    Deviation from the design doc's literal "frames paired by nearest
    timestamp" (disclosed, not silent): pairing uses each batch's
    *consumer-side arrival time* (`time.monotonic()` when `submit` is
    called), not the original frame-capture timestamp `FramePublisher`
    stamps at ingestion -- `FrameConsumer._process_message` doesn't
    currently read or forward that field to `DetectionPublisher.publish`
    for *any* camera type, and threading it through would mean touching
    frame_consumer.py's message-handling body, not just its constructor
    (unlike the one-line, fully backward-compatible `modality` addition
    above). Both consumers process messages from the same Redis instance
    in the same process at comparable cadence, so arrival time is a
    reasonable approximation for the "simple, not over-engineered" merge
    §6 explicitly calls for -- worth revisiting only if real-world testing
    shows the two streams drift enough for it to matter.

    A batch with no partner within tolerance publishes solo (unchanged),
    rather than being held indefinitely -- this is what makes §6 step 3's
    "thermal-only passes through" work, and applies the same courtesy to
    an RGB batch that arrives with no fresh-enough thermal partner instead
    of silently dropping it.
    """

    def __init__(
        self, *, camera_id: str, publisher: DetectionPublisher, settings: FusionSettings | None = None
    ) -> None:
        self._camera_id = camera_id
        self._publisher = publisher
        self._settings = settings or FusionSettings()
        self._rgb: tuple[float, list[Detection]] | None = None
        self._thermal: tuple[float, list[Detection]] | None = None

    async def submit(self, *, modality: str, detections: list[Detection], loop_generation: int) -> None:
        now = time.monotonic()
        if modality == "rgb":
            self._rgb = (now, detections)
            partner = self._thermal
            rgb_detections = detections
            thermal_detections = partner[1] if partner else []
        else:
            self._thermal = (now, detections)
            partner = self._rgb
            rgb_detections = partner[1] if partner else []
            thermal_detections = detections

        tolerance_s = self._settings.frame_sync_tolerance_ms / 1000
        if partner is not None and abs(now - partner[0]) <= tolerance_s:
            fused = merge_detections(rgb_detections, thermal_detections, self._settings)
        else:
            fused = detections  # no partner close enough in time -- pass through solo

        await self._publisher.publish(self._camera_id, fused, loop_generation=loop_generation)


class ModalityFeed:
    """Duck-typed as a `DetectionPublisher` (same `.publish(camera_id,
    detections, loop_generation=...)` shape) so an unmodified `FrameConsumer`
    can be pointed at it exactly like the real publisher -- it just forwards
    into the shared `FusionMerger` for this camera instead of writing
    anything to Redis itself."""

    def __init__(self, merger: FusionMerger, *, modality: str) -> None:
        self._merger = merger
        self._modality = modality

    async def publish(self, camera_id: str, detections: list[Detection], *, loop_generation: int = 0) -> None:
        del camera_id  # already bound on the shared FusionMerger
        await self._merger.submit(modality=self._modality, detections=detections, loop_generation=loop_generation)
