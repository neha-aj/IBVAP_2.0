"""Multi-camera pipeline load test (M10).

Validates SAS §11's backpressure/graceful-degradation claim: "if Detection
Service falls behind, ingestion continues live-preview but inference frame
rate degrades gracefully (frame skipping) rather than crashing."

Creates N synthetic file-source cameras via the real API, uploads a video to
each (so N independent ingestion/detection/tracking pipelines run
concurrently, all sharing detection-service's one inference worker), waits
for them to reach steady state, reads each camera's ingestion vs. detection
throughput from Prometheus (added during M10's own metrics work) plus each
stream's Redis consumer-group lag, then deletes every camera and its
tracks/events/alerts rows again so the run leaves no trace behind.

Usage (needs a video file to upload -- any short clip works):
    BASE=http://localhost:8080 PROMETHEUS=http://localhost:9090 \\
    python load_test_cameras.py /path/to/video.mp4 [num_cameras] [settle_seconds]

Requires the `redis-cli`/`psql` equivalents this script shells out to be
reachable -- simplest is to run it from a machine with `docker compose`
available in the project directory (it uses `docker compose exec redis ...`
directly), not from inside a container.
See `docs/load-test-report.md` for the results this produced (5 cameras).
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:8080")
PROMETHEUS = os.environ.get("PROMETHEUS", "http://localhost:9090")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "DevAdminPass123!")


def _post_json(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def login() -> str:
    return _post_json(f"{BASE}/api/v1/auth/login", {"username": "admin", "password": ADMIN_PASSWORD})["accessToken"]


def create_camera(token: str, name: str) -> str:
    req = urllib.request.Request(
        f"{BASE}/api/v1/cameras",
        data=json.dumps({"name": name, "location": "LoadTest", "type": "file"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["id"]


def upload_video(token: str, camera_id: str, video_path: str) -> None:
    # Delegates to curl for multipart -- stdlib's multipart support is
    # painful enough that shelling out is the pragmatic choice here.
    subprocess.run(
        [
            "curl", "-s", "-o", os.devnull, "-w", "%{http_code}",
            "-X", "POST", f"{BASE}/api/v1/cameras/{camera_id}/upload",
            "-H", f"Authorization: Bearer {token}",
            "-F", f"file=@{video_path};type=video/mp4",
        ],
        check=True,
        capture_output=True,
    )


def delete_camera(token: str, camera_id: str) -> None:
    req = urllib.request.Request(
        f"{BASE}/api/v1/cameras/{camera_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    urllib.request.urlopen(req)


def cleanup_history(camera_id: str) -> None:
    for table in ("tracks", "alerts", "events"):
        subprocess.run(
            ["docker", "compose", "exec", "postgres", "psql", "-U", "ibvap", "-d", "ibvap", "-c",
             f"DELETE FROM events.{table} WHERE camera_id='{camera_id}';"],
            capture_output=True,
        )


def prom_query(expr: str) -> list[dict]:
    with urllib.request.urlopen(f"{PROMETHEUS}/api/v1/query?query={urllib.parse.quote(expr)}") as resp:
        return json.loads(resp.read())["data"]["result"]


def stream_lag(camera_id: str, stream_suffix: str) -> int | None:
    result = subprocess.run(
        ["docker", "compose", "exec", "redis", "redis-cli", "XINFO", "GROUPS", f"cam:{camera_id}:{stream_suffix}"],
        capture_output=True, text=True,
    )
    lines = result.stdout.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "lag":
            return int(lines[i + 1].strip())
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    video_path = sys.argv[1]
    num_cameras = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    settle_seconds = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    token = login()
    camera_ids = []
    print(f"Creating {num_cameras} synthetic cameras from {video_path} ...")
    for i in range(num_cameras):
        cam_id = create_camera(token, f"LoadTest-{i}")
        upload_video(token, cam_id, video_path)
        camera_ids.append(cam_id)
        print(f"  {cam_id} ready")

    print(f"Settling for {settle_seconds}s ...")
    time.sleep(settle_seconds)

    print("\n--- per-camera throughput (fps) ---")
    ingestion_rates = {r["metric"]["camera_id"]: float(r["value"][1]) for r in prom_query(
        "sum by (camera_id) (rate(ingestion_frames_published_total[1m]))"
    )}
    detection_rates = {r["metric"]["camera_id"]: float(r["value"][1]) for r in prom_query(
        "sum by (camera_id) (rate(detection_frames_processed_total[1m]))"
    )}
    for cam_id in camera_ids:
        ing = ingestion_rates.get(cam_id, 0.0)
        det = detection_rates.get(cam_id, 0.0)
        ratio = f"{100 * det / ing:.0f}%" if ing else "n/a"
        frames_lag = stream_lag(cam_id, "frames")
        print(f"  {cam_id}: ingestion={ing:.2f} detection={det:.2f} ratio={ratio} frames_stream_lag={frames_lag}")

    print("\nCleaning up ...")
    for cam_id in camera_ids:
        delete_camera(token, cam_id)
        cleanup_history(cam_id)
    print("Done.")


if __name__ == "__main__":
    main()
