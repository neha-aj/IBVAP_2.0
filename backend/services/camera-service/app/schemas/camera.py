from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

CameraType = Literal["rtsp", "usb", "ip", "file", "webcam", "thermal", "dual"]
CameraStatus = Literal["online", "warning", "offline"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DetectionCounts(_CamelModel):
    """Always {0,0}: per Frontend Analysis Report §5.2, the frontend can
    derive these counts client-side from `GET /cameras/{id}/detections/current`
    (added in M4) just as easily, so the backend doesn't duplicate that
    computation here."""

    persons: int = 0
    vehicles: int = 0


class CameraCreate(_CamelModel):
    # Letters/digits/hyphen/underscore only -- this value ends up as a path
    # segment on disk (POST /cameras/{id}/upload stores under
    # `uploads/{id}/...`), so it must never carry `/`, `..`, or other
    # characters a filesystem path could interpret specially.
    external_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Display id, e.g. 'BOP-01-CAM-01'. Auto-generated if omitted.",
    )
    name: str
    location: str
    sector: str | None = Field(default=None, description="Sector name or code; created if new.")
    type: CameraType
    source_url: str | None = Field(
        default=None,
        description="RTSP/ONVIF URL, USB device index, uploaded file path, or webcam device URI. "
        "For type='file', leave empty and use POST /cameras/{id}/upload instead.",
    )
    thermal_source_url: str | None = Field(
        default=None,
        description="Thermal stream URL -- required (alongside source_url) when type='dual'. "
        "Unused for every other type.",
    )


class Calibration(_CamelModel):
    """A one-time admin-configured pixel-to-real-world mapping (Phase 2
    doc09 §1.2 Speed Estimation): two reference points a known real-world
    distance apart, plus the speed threshold that should flag a `Speed
    Violation`. `pixel_distance` is in the same percentage-of-frame units
    every other bbox/polygon coordinate already uses."""

    pixel_distance: float = Field(gt=0)
    real_world_meters: float = Field(gt=0)
    threshold_kmh: float = Field(gt=0)


class CameraUpdate(_CamelModel):
    name: str | None = None
    location: str | None = None
    sector: str | None = None
    source_url: str | None = None
    thermal_source_url: str | None = None
    calibration: Calibration | None = None


class CameraRead(_CamelModel):
    id: str  # external_id -- the id the frontend/rest of the pipeline uses everywhere
    name: str
    location: str
    sector: str | None
    status: CameraStatus
    resolution: str | None
    fps: int
    last_active: str | None  # formatted "HH:MM:SS" to match mockCameras.lastActive exactly
    detections: DetectionCounts
    alert: str | None
    type: CameraType
    # M11: additive -- only meaningful for type='dual'; None for every other
    # camera. Placed on CameraRead (not just CameraDetail, unlike source_url)
    # so the surveillance list view can show a thermal indicator without a
    # detail-view round trip.
    thermal_source_url: str | None = None


class CameraDetail(CameraRead):
    """Adds fields used by the Surveillance page's CameraDetails panel."""

    source_url: str | None
    connection: str  # "Stable" | "Disconnected", derived from status
    calibration: Calibration | None = None


class CameraStatusSummary(_CamelModel):
    online: int
    warning: int
    offline: int
    total: int


class CameraListResponse(_CamelModel):
    items: list[CameraRead]
    total: int
    page: int
    page_size: int


class StreamInfo(_CamelModel):
    mjpeg_url: str
    hls_url: str | None = None
