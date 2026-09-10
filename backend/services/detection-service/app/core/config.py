from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "detection-service"

    # Camera Management Service (M2) -- source of truth for which cameras
    # exist, used the same way Ingestion (M3) discovers cameras to open.
    camera_service_url: str = "http://camera-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group (SAS §5.2, §11 at-least-once processing).
    consumer_group_name: str = "detection-service"
    frames_read_count: int = 5
    frames_block_ms: int = 2000

    # How many entries to keep per `cam:{id}:detections` stream before
    # trimming (SAS §11 backpressure), mirroring ingestion's frame_stream_maxlen.
    detections_stream_maxlen: int = 500

    # TTL on the `cam:{id}:current_detections` cache key that powers
    # `GET /cameras/{id}/detections/current` and the live overlay -- short
    # enough that a stalled/offline camera's overlay clears itself rather
    # than showing stale boxes forever.
    current_detections_ttl_seconds: int = 5

    # Inference tuning. Ultralytics downloads this on first use if missing --
    # pointed at the mounted `detection-models` volume (docker-compose.yml)
    # so the ~6MB download survives container recreation.
    # yolov8s (small) over the default yolov8n (nano) -- meaningfully better
    # recall on small/distant objects (e.g. a background vehicle) at a still
    # CPU-feasible cost for this low-fps pipeline.
    model_path: str = "/srv/models/yolov8s.pt"
    confidence_threshold: float = 0.4
    # Backend selection: "onnx" requires an exported .onnx at `onnx_model_path`
    # and the optional `onnx` dependency group; otherwise falls back to the
    # Ultralytics/torch runner (GPU if available, else CPU) -- SAS §3/§9
    # "GPU if available, ONNX Runtime CPU fallback".
    inference_backend: str = "auto"
    onnx_model_path: str = "/srv/models/yolov8n.onnx"
    onnx_input_size: int = 640

    # --- M11 thermal fusion (SAS M11 §6) -- only exercised for 'dual'
    # cameras; every other camera type's inference/publish path is
    # completely unaffected by these. ---
    fusion_frame_sync_tolerance_ms: float = 150.0
    fusion_low_conf_threshold: float = 0.35
    fusion_confidence_boost: float = 0.25
    fusion_suppress_threshold: float = 0.25
    # Not in the design doc's own list of named env vars, but §6 step 2's
    # ">30% bbox IoU" needs a concrete constant somewhere -- kept next to
    # the other fusion tunables rather than hardcoded in fusion_merger.py.
    fusion_min_iou: float = 0.30

    # --- M11 edge deployment profile (SAS M11 §7) ---
    # 'central' (default, unchanged Phase 1/2 behavior): DetectionPublisher
    # writes straight to the central Redis Streams instance, exactly as
    # every service in this project already does. 'edge': detections queue
    # in a local SQLite outbox instead (see edge_outbox.py) and a separate
    # sync_worker drains them to central Redis in the background, tolerant
    # of the link being down.
    deployment_mode: str = "central"
    edge_outbox_path: str = "/data/edge_outbox.db"
    edge_sync_batch_size: int = 100
    edge_sync_interval_seconds: float = 5.0
    edge_sync_initial_backoff_seconds: float = 1.0
    edge_sync_max_backoff_seconds: float = 60.0
    # Minimal local rule engine (zone-intrusion + count-threshold only --
    # §7's own scope, a strict subset of event-alert-service's real rule
    # engine) that runs against the local outbox so a site can still raise
    # a local alert during a full connectivity outage. Off by default --
    # 'edge' mode alone only changes where detections queue, not whether
    # anything evaluates rules against them locally.
    edge_local_rules: bool = False
    edge_local_rules_count_threshold: int = 5
    edge_local_rules_count_window_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
