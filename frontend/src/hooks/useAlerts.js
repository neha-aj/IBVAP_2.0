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
      setAlerts((current) => [alert, ...current]);
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
