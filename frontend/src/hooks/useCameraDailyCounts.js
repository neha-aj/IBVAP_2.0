import { useEffect, useState } from "react";
import { analyticsService } from "../services/analyticsService";

const REFRESH_INTERVAL_MS = 30_000;

// Per-camera "how many distinct people/vehicles today" -- a cumulative
// daily total (same source as the Dashboard's all-cameras sum), not the
// live in-frame count `useDetections` provides. No WS topic backs this
// (it's a daily aggregate, not a discrete event), so it's a plain polled
// fetch instead of a live subscription.
export function useCameraDailyCounts() {
  const [countsByCameraId, setCountsByCameraId] = useState({});

  useEffect(() => {
    let cancelled = false;

    function load() {
      analyticsService
        .getPeopleVehiclesByCamera()
        .then((rows) => {
          if (cancelled) return;
          setCountsByCameraId(Object.fromEntries(rows.map((r) => [r.cameraId, r])));
        })
        .catch(() => {});
    }

    load();
    const interval = setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return countsByCameraId;
}
