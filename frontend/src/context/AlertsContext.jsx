import { createContext, useContext, useEffect, useState } from "react";
import { alertService } from "../services/alertService";
import { socket } from "../services/socket";
import { AuthContext } from "./AuthContext";

export const AlertsContext = createContext(null);

// Same reasoning as useEvents.js's own MAX_LIVE_EVENTS: without a cap this
// array would grow forever for as long as the app stays open, since new
// alerts keep streaming in over the WebSocket long after the initial page
// load -- useAlerts.js was missing this cap entirely (an oversight relative
// to useEvents.js, not a deliberate difference).
const MAX_LIVE_ALERTS = 300;

// Previously `useAlerts()` did its own fetch + its own WebSocket
// subscription every time it was called -- and it's called from Sidebar
// (mounted on every page), Dashboard, and the Alerts page, so a single
// session ran three independent, ever-growing copies of the same alerts
// list at once, each re-rendering on every incoming alert. Centralizing the
// fetch/subscription here (one copy, shared via context) is what actually
// fixed the site-wide slowness -- `useAlerts()` below is now just a thin
// read of this shared state, so none of its existing callers need to change.
export function AlertsProvider({ children }) {
  const { status } = useContext(AuthContext);
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await alertService.getAll();
        if (!cancelled) setAlerts(data);
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
  }, [status]);

  useEffect(() => {
    if (status !== "authenticated") return;
    socket.subscribe(["alerts"]);

    const offNew = socket.on("alert.new", (alert) => {
      // Guards against a duplicate entry (-> React "two children with the
      // same key" warning, and a genuinely duplicated card) when this push
      // races the initial `alertService.getAll()` load.
      setAlerts((current) =>
        current.some((a) => a.id === alert.id) ? current : [alert, ...current].slice(0, MAX_LIVE_ALERTS)
      );
    });
    const offUpdated = socket.on("alert.updated", (alert) => {
      setAlerts((current) => current.map((a) => (a.id === alert.id ? alert : a)));
    });

    return () => {
      offNew();
      offUpdated();
      socket.unsubscribe(["alerts"]);
    };
  }, [status]);

  return (
    <AlertsContext.Provider value={{ alerts, setAlerts, isLoading, error }}>
      {children}
    </AlertsContext.Provider>
  );
}
