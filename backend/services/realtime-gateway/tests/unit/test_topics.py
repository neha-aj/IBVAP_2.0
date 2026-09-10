from app.ws.topics import camera_topic, is_valid_topic


def test_alerts_and_events_are_valid() -> None:
    assert is_valid_topic("alerts") is True
    assert is_valid_topic("events") is True


def test_system_is_valid() -> None:
    """Phase 2 M24 -- backs the `system.health` topic."""
    assert is_valid_topic("system") is True


def test_camera_topic_is_valid() -> None:
    assert is_valid_topic("camera:FILE-01") is True


def test_bare_camera_prefix_without_id_is_invalid() -> None:
    assert is_valid_topic("camera:") is False


def test_unknown_topic_is_invalid() -> None:
    assert is_valid_topic("something-else") is False


def test_camera_topic_helper_builds_expected_name() -> None:
    assert camera_topic("FILE-01") == "camera:FILE-01"
