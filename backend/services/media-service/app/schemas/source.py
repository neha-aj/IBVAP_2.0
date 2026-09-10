from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceStored(_CamelModel):
    """Phase 2 M23: `POST /internal/media/sources` returns `{path}` -- a
    raw filesystem path (not a URL, unlike every other media type this
    service stores), since Ingestion Service reads a `file`-type camera's
    source straight off disk (`cv2.VideoCapture(path)`), never over HTTP.
    """

    path: str
