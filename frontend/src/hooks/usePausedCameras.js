import { useCallback, useEffect, useRef, useState } from "react";
import { cameraService } from "../services/cameraService";

// How often to re-read the paused set, so a pause/resume done from another
// browser tab (or another operator) shows up here without a reload.
const SYNC_INTERVAL_MS = 10000;

// Which cameras an operator has paused. The source of truth is the backend
// (a paused camera's frames stop reaching the analysis pipeline), so this
// just mirrors it: toggling is optimistic for a snappy UI and rolls back if
// the request fails (e.g. a viewer-role account without pause permission).
export function usePausedCameras() {
  const [pausedIds, setPausedIds] = useState(() => new Set());
  const [error, setError] = useState(null);
  // Ids with a toggle request in flight -- a poll landing mid-request must
  // not overwrite the optimistic state for them.
  const pendingRef = useRef(new Set());

  useEffect(() => {
    let cancelled = false;

    async function sync() {
      try {
        const ids = await cameraService.getPaused();
        if (cancelled) return;
        setPausedIds((current) => {
          const next = new Set(ids);
          for (const id of pendingRef.current) {
            if (current.has(id)) next.add(id);
            else next.delete(id);
          }
          return next;
        });
      } catch {
        // Best-effort: a failed poll just leaves the last known state.
      }
    }

    sync();
    const timer = setInterval(sync, SYNC_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const togglePause = useCallback(
    async (cameraId) => {
      if (pendingRef.current.has(cameraId)) return;
      const willPause = !pausedIds.has(cameraId);
      pendingRef.current.add(cameraId);
      setError(null);
      setPausedIds((current) => {
        const next = new Set(current);
        if (willPause) next.add(cameraId);
        else next.delete(cameraId);
        return next;
      });
      try {
        if (willPause) await cameraService.pause(cameraId);
        else await cameraService.resume(cameraId);
      } catch (err) {
        setPausedIds((current) => {
          const next = new Set(current);
          if (willPause) next.delete(cameraId);
          else next.add(cameraId);
          return next;
        });
        setError(
          err?.status === 403
            ? "Your account doesn't have permission to pause cameras."
            : `Couldn't ${willPause ? "pause" : "resume"} ${cameraId}. Please try again.`
        );
      } finally {
        pendingRef.current.delete(cameraId);
      }
    },
    [pausedIds]
  );

  return { pausedIds, togglePause, error, clearError: () => setError(null) };
}
