import { useEffect, useState } from "react";
import { systemService } from "../services/systemService";
import { socket } from "../services/socket";

// The `system.health` WS topic only ever carries *future* status changes
// (see realtime-gateway's HealthPoller docstring) -- so the initial REST
// fetch is what tells a freshly-opened page current state; the socket
// keeps it live from there.
export function useSystemHealth() {
  const [statusByService, setStatusByService] = useState({});

  useEffect(() => {
    let cancelled = false;
    systemService
      .getHealth()
      .then((rows) => {
        if (cancelled) return;
        setStatusByService(Object.fromEntries(rows.map((r) => [r.service, r.status])));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    socket.subscribe(["system"]);
    const off = socket.on("system.health", ({ service, status }) => {
      setStatusByService((current) => ({ ...current, [service]: status }));
    });
    return () => {
      off();
      socket.unsubscribe(["system"]);
    };
  }, []);

  const services = Object.entries(statusByService);
  const downServices = services.filter(([, status]) => status !== "up").map(([name]) => name);

  return {
    isChecking: services.length === 0,
    isOperational: services.length > 0 && downServices.length === 0,
    downServices,
  };
}
