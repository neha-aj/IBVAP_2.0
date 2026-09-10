from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.camera import Calibration, CameraStatus, CameraType


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class InternalCameraConfig(_CamelModel):
    """What the Stream Ingestion Service needs to open a source -- includes
    `source_url`, which the public CameraRead schema deliberately omits from
    list views. `name`/`location` are additionally used by the Event/Alert
    Service (M6) to denormalize onto events/alerts without a separate
    per-camera call to a JWT-protected public endpoint (internal callers
    only carry the M2M token, not a user's bearer token)."""

    id: str  # external_id
    name: str
    location: str
    type: CameraType
    source_url: str | None
    # M11: only set for type='dual' -- the Stream Ingestion Service opens a
    # second capture worker against this URL alongside source_url.
    thermal_source_url: str | None = None
    # Phase 2 M14 Speed Estimation: the Event/Alert Service needs this to
    # convert pixel displacement into a real-world speed.
    calibration: Calibration | None = None


class CameraStatusUpdate(_CamelModel):
    status: CameraStatus
    fps: int | None = None
