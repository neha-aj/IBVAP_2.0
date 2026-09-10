import { useEffect, useRef, useState } from "react";
import { cameraService } from "../services/cameraService";
import { socket } from "../services/socket";

// How long a track is kept showing after its last `detection.new` mention
// before it's dropped. Each message is one video frame's worth of boxes,
// so a single missed frame (occlusion, motion blur, a low-confidence frame)
// used to make a person vanish from the count and reappear a moment later
// -- visible as the per-camera counts flickering rapidly. Holding a track
// for a short grace window smooths that out while still dropping it
// reasonably quickly once it's actually gone.
const TRACK_GRACE_MS = 1500;
const PURGE_INTERVAL_MS = 500;

// Detections are inherently per-camera (API Spec §2/§8) -- there is no
// "all detections across every camera" endpoint or topic. `cameraIds` is
// the set of cameras currently rendered (the surveillance grid); this hook
// fetches each one's current detections once, then keeps them live via
// each camera's own `camera:{id}` `detection.new` topic, and flattens the
// result into one array so existing per-camera filtering (`CameraGrid`,
// `DetectionSummary`) keeps working unchanged.
export function useDetections(cameraIds = []) {
  // { [cameraId]: { [trackId or detectionId]: { detection, lastSeenAt } } }
  const [tracksByCamera, setTracksByCamera] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [, forceTick] = useState(0);
  const subscribedIds = useRef(new Set());
  const idsKey = cameraIds.join(",");

  useEffect(() => {
    if (cameraIds.length === 0) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      const results = await Promise.all(
        cameraIds.map(async (id) => {
          try {
            return [id, await cameraService.getCurrentDetections(id)];
          } catch {
            return [id, []];
          }
        })
      );
      if (!cancelled) {
        const now = Date.now();
        setTracksByCamera(
          Object.fromEntries(
            results.map(([id, detections]) => [
              id,
              Object.fromEntries(
                detections.map((d) => [d.trackId ?? d.id, { detection: d, lastSeenAt: now }])
              ),
            ])
          )
        );
        setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  useEffect(() => {
    const currentIds = new Set(cameraIds);
    const toSubscribe = [...currentIds].filter((id) => !subscribedIds.current.has(id));
    const toUnsubscribe = [...subscribedIds.current].filter((id) => !currentIds.has(id));

    if (toSubscribe.length > 0) socket.subscribe(toSubscribe.map((id) => `camera:${id}`));
    if (toUnsubscribe.length > 0) socket.unsubscribe(toUnsubscribe.map((id) => `camera:${id}`));

    subscribedIds.current = currentIds;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  useEffect(() => {
    return socket.on("detection.new", ({ cameraId, detections }) => {
      const now = Date.now();
      setTracksByCamera((current) => {
        const tracks = { ...(current[cameraId] || {}) };
        detections.forEach((d) => {
          tracks[d.trackId ?? d.id] = { detection: d, lastSeenAt: now };
        });
        return { ...current, [cameraId]: tracks };
      });
    });
  }, []);

  // Tracks age out of the grace window even if no further message ever
  // arrives for them (e.g. the object actually left) -- a periodic tick
  // re-renders so `now - lastSeenAt` below gets re-evaluated on its own,
  // not just when a new message happens to arrive.
  useEffect(() => {
    const interval = setInterval(() => forceTick((t) => t + 1), PURGE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const now = Date.now();
  const detections = Object.values(tracksByCamera).flatMap((tracks) =>
    Object.values(tracks)
      .filter((entry) => now - entry.lastSeenAt <= TRACK_GRACE_MS)
      .map((entry) => entry.detection)
  );

  return { detections, isLoading };
}
