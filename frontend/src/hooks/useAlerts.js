import { useContext } from "react";
import { AlertsContext } from "../context/AlertsContext";

// Thin read of the shared AlertsProvider (see context/AlertsContext.jsx for
// why this moved out of a per-call-site fetch+subscription) -- every
// existing caller (Sidebar, Dashboard, the Alerts page) keeps working
// unchanged, they just now all share one underlying fetch/subscription
// instead of each running their own.
export function useAlerts() {
  const ctx = useContext(AlertsContext);
  if (!ctx) {
    throw new Error("useAlerts must be used within an AlertsProvider");
  }
  return ctx;
}
