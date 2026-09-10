from pathlib import Path

import pytest

from app.inference.edge_outbox import EdgeOutbox
from app.inference.local_rules import LocalRuleEngine, point_in_polygon
from app.schemas.detection import BoundingBox, Detection


def _detection(id: str = "d1", *, x: float = 50.0, y: float = 50.0) -> Detection:
    return Detection(id=id, camera_id="CAM-01", type="person", confidence=0.9, bbox=BoundingBox(x=x, y=y, width=2, height=2))


def test_point_in_polygon_inside() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon(5, 5, square) is True


def test_point_in_polygon_outside() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon(50, 50, square) is False


def test_count_threshold_fires_once_over_the_limit() -> None:
    engine = LocalRuleEngine(count_threshold=3, count_window_seconds=60.0)

    fired = []
    for _ in range(4):
        fired = engine.evaluate(camera_id="CAM-01", detections=[_detection()])

    assert any(a["event_type"] == "Count Threshold Exceeded" for a in fired)


def test_count_threshold_does_not_fire_under_the_limit() -> None:
    engine = LocalRuleEngine(count_threshold=10, count_window_seconds=60.0)

    fired = engine.evaluate(camera_id="CAM-01", detections=[_detection()])

    assert fired == []


def test_zone_intrusion_fires_when_detection_center_is_inside_a_restricted_zone() -> None:
    zones = {
        "CAM-01": [
            {"id": "z1", "name": "No-Go Area", "zone_type": "restricted", "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)]}
        ]
    }
    engine = LocalRuleEngine(count_threshold=999, count_window_seconds=60.0, zones_by_camera=zones)

    fired = engine.evaluate(camera_id="CAM-01", detections=[_detection(x=50, y=50)])

    assert any(a["event_type"] == "Restricted Zone Entry" for a in fired)


def test_zone_intrusion_does_not_fire_outside_the_zone() -> None:
    zones = {
        "CAM-01": [
            {"id": "z1", "name": "No-Go Area", "zone_type": "restricted", "polygon": [(0, 0), (10, 0), (10, 10), (0, 10)]}
        ]
    }
    engine = LocalRuleEngine(count_threshold=999, count_window_seconds=60.0, zones_by_camera=zones)

    fired = engine.evaluate(camera_id="CAM-01", detections=[_detection(x=90, y=90)])

    assert fired == []


def test_zone_intrusion_ignores_non_restricted_zones() -> None:
    zones = {"CAM-01": [{"id": "z1", "name": "Queue", "zone_type": "queue", "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)]}]}
    engine = LocalRuleEngine(count_threshold=999, count_window_seconds=60.0, zones_by_camera=zones)

    fired = engine.evaluate(camera_id="CAM-01", detections=[_detection(x=50, y=50)])

    assert fired == []


@pytest.mark.asyncio
async def test_evaluate_and_record_persists_fired_alerts_and_dedupes(tmp_path: Path) -> None:
    outbox = EdgeOutbox(str(tmp_path / "edge_outbox.db"))
    zones = {
        "CAM-01": [
            {"id": "z1", "name": "No-Go Area", "zone_type": "restricted", "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)]}
        ]
    }
    engine = LocalRuleEngine(count_threshold=999, count_window_seconds=60.0, zones_by_camera=zones)
    det = _detection(id="d1", x=50, y=50)

    recorded_first = await engine.evaluate_and_record(camera_id="CAM-01", detections=[det], outbox=outbox)
    recorded_second = await engine.evaluate_and_record(camera_id="CAM-01", detections=[det], outbox=outbox)

    assert recorded_first == 1
    assert recorded_second == 0  # same detection id -- same idempotency key, already recorded
    assert await outbox.count_pending_local_alerts() == 1
