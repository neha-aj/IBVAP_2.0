import { useEffect, useRef, useState } from "react";
import { socket } from "../services/socket";

// Mirrors useDetections.js's own grace-window/eviction logic exactly, just
// for `pose.updated` instead of `detection.new` -- see that hook's comment
// for why a grace window exists at all (a single missed frame shouldn't
// make a badge flicker off and back on). Kept as its own constant (not
// imported from useDetections.js) since pose-service samples at a slower
// interval (1.5s default vs. detection-service's ~3fps) -- see
// services/pose-service/app/core/config.py's own comment on why -- so a
// pose reading realistically goes quiet for longer between messages even
// when nothing has changed; a shared constant tuned for the faster stream
// would evict poses prematurely.
const POSE_GRACE_MS = 3000;
const PURGE_INTERVAL_MS = 500;

// Poses are display-only and ephemeral by design (never persisted --
// services/pose-service/app/core/config.py) -- unlike useDetections.js,
// there is no `GET .../poses/current` to seed initial state from; this
// hook only ever reflects whatever `pose.updated` messages have arrived
// live since it mounted, which is exactly right for a live-video-overlay
// concept, not an event/alert concept.
export function usePoses(cameraIds = []) {
  // { [cameraId]: [{ x, y, posture, confidence, lastSeenAt }] }
  const [posesByCamera, setPosesByCamera] = useState({});
  const [, forceTick] = useState(0);
  const subscribedIds = useRef(new Set());
  const idsKey = cameraIds.join(",");

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
    return socket.on("pose.updated", ({ cameraId, poses }) => {
      const now = Date.now();
      setPosesByCamera((current) => ({
        ...current,
        [cameraId]: (poses || []).map((p) => ({ ...p, lastSeenAt: now })),
      }));
    });
  }, []);

  // Same reasoning as useDetections.js: a periodic tick re-renders so
  // `now - lastSeenAt` below gets re-evaluated even with no new message.
  useEffect(() => {
    const interval = setInterval(() => forceTick((t) => t + 1), PURGE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const now = Date.now();
  const posesByCameraFresh = Object.fromEntries(
    Object.entries(posesByCamera).map(([cameraId, poses]) => [
      cameraId,
      poses.filter((p) => now - p.lastSeenAt <= POSE_GRACE_MS),
    ])
  );

  return { posesByCamera: posesByCameraFresh };
}
