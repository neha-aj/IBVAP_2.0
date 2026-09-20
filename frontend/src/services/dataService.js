import { api } from "./api";

// Housekeeping for the Events / Alerts data (Settings page). `reset` deletes
// events + alerts and, in the background, their evidence files; admin only.
export const dataService = {
  getSummary: () => api.get("/events/data/summary"),
  // olderThanDays omitted/null = everything. only: "direction_images" deletes just the
  // snapshot images of Direction Observed events and keeps every event and alert.
  // `confirm` must be exactly "RESET".
  reset: ({ olderThanDays, only, confirm }) =>
    api.post("/events/data/reset", { olderThanDays: olderThanDays || null, only: only || null, confirm }),
};
