from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "reid-service"
    db_schema: str = "reid"

    camera_service_url: str = "http://camera-service:8000"
    ingestion_service_url: str = "http://ingestion-service:8000"
    media_service_url: str = "http://media-service:8000"
    event_alert_service_url: str = "http://event-alert-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:tracks` (doc09 §2.2: "on
    # each new track, requests a representative crop... extracts an
    # embedding vector") -- its own consumer group, independent of
    # event-alert-service's own group on the same stream (SAS §11: multiple
    # consumer groups on one stream is the documented pattern for this).
    consumer_group_name: str = "reid-service"
    tracks_read_count: int = 10
    tracks_block_ms: int = 2000

    # --- Embedding model (doc11 §2) ---
    # ImageNet-pretrained ResNet-50, doc11's own documented fallback when no
    # fine-tuned OSNet/TorchReID weights exist for this deployment -- see
    # app/inference/embedder.py's docstring. 2048 is that model's natural
    # pooled-feature dimension (doc09's literal `vector(512)` spec assumed a
    # dedicated Re-ID model with a smaller projection head; documented
    # deviation, same discipline as every other spec-vs-reality gap this
    # project has recorded).
    embedding_dimension: int = 2048
    person_crop_min_size_px: int = 32
    # Phase 2 M17 (Vehicle Re-ID): vehicles typically occupy a larger share
    # of frame than people at the same distance, so a separate (higher)
    # floor avoids embedding tiny, far-away/partial vehicle crops that would
    # mostly add noise to the similarity index.
    vehicle_crop_min_size_px: int = 40

    # doc11 §2: "default suggested 0.6-0.7 cosine similarity, tunable -- no
    # single correct value, must be validated against the actual camera set
    # during rollout". Cosine *similarity* here (1 - cosine distance).
    similarity_threshold: float = 0.6
    max_search_results: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
