from functools import lru_cache

from ibvap_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "pose-service"
    # No db_schema override, no repository/model package anywhere in this
    # service -- same reasoning as fire-smoke-service's config.py: this is a
    # DISPLAY-ONLY live overlay (per-person posture: standing/sitting/
    # sleeping), never persisted to Postgres or any other store. Not even an
    # event/alert is reported for it (unlike fire-smoke-service, which does
    # report through event-alert-service) -- a posture reading has no
    # "incident" semantics, it's ephemeral the same way a video frame itself
    # is. CommonSettings.postgres_* fields still exist only because
    # docker-compose's shared env block sets them for every service
    # uniformly; nothing here ever opens a DB connection with them.

    camera_service_url: str = "http://camera-service:8000"
    camera_refresh_interval_seconds: int = 15

    # Redis Streams consumer group on `cam:{id}:frames` -- independent of
    # detection-service's and fire-smoke-service's own groups on the same
    # stream (SAS §11: multiple consumer groups per stream is the supported
    # pattern for this).
    consumer_group_name: str = "pose-service"
    frames_read_count: int = 5
    frames_block_ms: int = 2000

    # Pose classification (MediaPipe PoseLandmarker + joint-angle geometry)
    # is meaningfully more expensive per-frame than fire-smoke-service's
    # pure color/shape heuristics -- a real landmark-detection model runs
    # per sampled frame, not a handful of cv2 color-mask/contour calls -- so
    # this defaults to a slower sample rate than fire-smoke-service's 0.3s
    # (~3fps). Posture also changes on a human timescale (seconds), not a
    # fire/smoke-developing-rapidly timescale, so there's no accuracy
    # argument for sampling faster even if the budget allowed it.
    sample_interval_seconds: float = 1.5

    # MediaPipe Tasks API PoseLandmarker's own per-pose detection-confidence
    # floor -- readings below this are dropped before classification/publish
    # rather than being published as a low-confidence badge (this is a live
    # overlay; a wrong or flickering badge is worse than a missing one).
    min_pose_confidence: float = 0.5

    # Multi-person cap passed to PoseLandmarker's `num_poses` -- bounds the
    # per-frame inference cost; a typical camera view (perimeter/entryway,
    # per doc09's own framing) rarely has more people in frame than this at
    # once, and MediaPipe's `num_poses` argument requires a fixed ceiling.
    max_poses_per_frame: int = 8

    # Path to the MediaPipe Tasks `.task` model bundle (downloaded at image
    # build time -- see Dockerfile). Not bundled inside `app/` itself for
    # the same reason detection-service/reid-service keep their own model
    # weights out of the app package: a binary model file doesn't belong
    # inside application source.
    pose_model_path: str = "/srv/models/pose_landmarker.task"

    # --- Posture-classification geometry thresholds (see
    # app/inference/pose_classifier.py's own docstring for the full
    # reasoning behind each). Not tuned against a labeled posture dataset
    # (none exists for this deployment) -- chosen from the standard
    # human-pose-estimation literature's own conventions for "upright torso"
    # / "bent knee" / "prone" angle bands, same honest-disclosure spirit as
    # fire-smoke-service's own heuristic thresholds. ---

    # Torso-vertical angle (shoulder-midpoint -> hip-midpoint vector vs. the
    # image's vertical/gravity axis), degrees. Below this, the torso reads
    # as upright.
    torso_vertical_max_degrees: float = 35.0
    # Above this, the torso reads as flat/horizontal (lying down).
    torso_horizontal_min_degrees: float = 60.0
    # Hip-knee-ankle bend angle, degrees. A straight leg is ~180 degrees;
    # below this it counts as "bent" (seated).
    knee_bend_max_degrees: float = 155.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
