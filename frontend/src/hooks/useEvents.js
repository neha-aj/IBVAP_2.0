import { useEffect, useState } from "react";
import { eventService } from "../services/eventService";
import { socket } from "../services/socket";

// A live camera feed can emit informational events (e.g. "Direction
// Observed") several times a second per moving object -- without a cap
// this array would grow forever for as long as the page stays open,
// eventually showing an unusably huge "number of events" to the user even
// though the backend itself only keeps the most recent page server-side.
const MAX_LIVE_EVENTS = 200;

export function useEvents() {
  const [events, setEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await eventService.getAll();
        if (!cancelled) setEvents(data);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    socket.subscribe(["events"]);
    const offNew = socket.on("event.new", (event) => {
      // Same duplicate-entry guard as useAlerts.js's "alert.new" handler --
      // this push can race the initial `eventService.getAll()` load.
      setEvents((current) =>
        current.some((e) => e.id === event.id) ? current : [event, ...current].slice(0, MAX_LIVE_EVENTS)
      );
    });
    return () => {
      offNew();
      socket.unsubscribe(["events"]);
    };
  }, []);

  return { events, isLoading, error };
}
