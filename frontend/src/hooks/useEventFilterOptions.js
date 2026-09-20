import { useEffect, useState } from "react";
import { cameraService } from "../services/cameraService";
import { eventService } from "../services/eventService";

const REFRESH_MS = 30000;

// Choices for the Events page dropdowns: cameras, event types and severities
// that actually occur in the stored events (with how many), so nothing in a
// dropdown can lead to an empty list -- except cameras, where every camera
// that currently exists is offered even if it hasn't produced an event yet.
export function useEventFilterOptions() {
  const [options, setOptions] = useState({ cameras: [], eventTypes: [], severities: [] });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [fromEvents, liveCameras] = await Promise.all([
        eventService.getFilterOptions().catch(() => null),
        cameraService.getAll().catch(() => []),
      ]);
      if (cancelled || !fromEvents) return;

      // Cameras that have events (including since-deleted ones, whose history
      // is still stored) plus every camera that exists now.
      const byId = new Map(fromEvents.cameras.map((c) => [c.id, { id: c.id, name: c.name, count: c.count }]));
      for (const camera of liveCameras) {
        if (!byId.has(camera.id)) byId.set(camera.id, { id: camera.id, name: camera.name, count: 0 });
      }
      const cameras = [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));

      setOptions({ cameras, eventTypes: fromEvents.eventTypes, severities: fromEvents.severities });
    }

    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return options;
}
