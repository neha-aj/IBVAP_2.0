import { useEffect, useState } from "react";
import { alertService } from "../services/alertService";
import { socket } from "../services/socket";

export function useAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
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
  }, []);

  useEffect(() => {
    socket.subscribe(["alerts"]);

    const offNew = socket.on("alert.new", (alert) => {
      // Guards against a duplicate entry (-> React "two children with the
      // same key" warning, and a genuinely duplicated card) when this push
      // races the initial `alertService.getAll()` load -- both can resolve
      // with the same just-created alert.
      setAlerts((current) => (current.some((a) => a.id === alert.id) ? current : [alert, ...current]));
    });
    const offUpdated = socket.on("alert.updated", (alert) => {
      setAlerts((current) => current.map((a) => (a.id === alert.id ? alert : a)));
    });

    return () => {
      offNew();
      offUpdated();
      socket.unsubscribe(["alerts"]);
    };
  }, []);

  return { alerts, setAlerts, isLoading, error };
}
