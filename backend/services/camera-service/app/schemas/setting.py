from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SettingValue(_CamelModel):
    key: str
    value: dict[str, Any]


class SettingsGroup(_CamelModel):
    group: str
    items: list[SettingValue]


class SettingUpdate(_CamelModel):
    value: dict[str, Any]


# Defaults seeded on first startup, matching every toggle/row shown on the
# Settings page (Frontend Analysis Report §3.7) so the page renders real,
# meaningful data immediately instead of empty groups.
DEFAULT_SETTINGS: dict[str, dict[str, dict[str, Any]]] = {
    "system": {
        "systemStatus": {"value": "operational"},
        "deploymentMode": {"value": "edge deployment"},
        "serverStatus": {"value": "available"},
    },
    "detection": {
        "humanDetection": {"enabled": True},
        "vehicleDetection": {"enabled": True},
        "anpr": {"enabled": False},
        "faceDetection": {"enabled": False},
        "intrusionDetection": {"enabled": True},
        "nightDetection": {"enabled": True},
    },
    "alerts": {
        "alertNotifications": {"enabled": True},
        "alertSeverityThreshold": {"value": "medium"},
        "eventRetention": {"value": "30d"},
    },
    "camera": {
        "cameraConfiguration": {"value": "default"},
        "streamConfiguration": {"value": "default"},
    },
}
