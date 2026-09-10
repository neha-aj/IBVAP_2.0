"""Topic naming (API Spec §8): `alerts`, `events` are global; `camera:{id}`
is per-camera. Client subscribes to whichever topics it cares about --
e.g. a viewer looking at one camera's Surveillance tile subscribes to
`camera:{id}` alone, not every camera's detection stream."""

from __future__ import annotations

_STATIC_TOPICS = {"alerts", "events", "system"}
_CAMERA_TOPIC_PREFIX = "camera:"


def is_valid_topic(topic: str) -> bool:
    if topic in _STATIC_TOPICS:
        return True
    return topic.startswith(_CAMERA_TOPIC_PREFIX) and len(topic) > len(_CAMERA_TOPIC_PREFIX)


def camera_topic(camera_id: str) -> str:
    return f"{_CAMERA_TOPIC_PREFIX}{camera_id}"
