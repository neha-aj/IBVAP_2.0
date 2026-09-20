// Shared by the Events page's dropdowns, its server queries, its live-update
// filtering and its export -- one definition of what each filter means, so the
// table, the count and the exported file can never disagree.

export const EMPTY_FILTERS = {
  camera: "",
  eventType: "",
  severity: "",
  datePreset: "all",
  customFrom: "", // yyyy-mm-dd, local
  customTo: "",
};

export const DATE_PRESETS = [
  { value: "all", label: "All dates" },
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last7", label: "Last 7 days" },
  { value: "last30", label: "Last 30 days" },
  { value: "custom", label: "Custom range..." },
];

export const SEVERITY_LABELS = { critical: "Critical", high: "High", medium: "Medium", low: "Low" };

function startOfDay(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function daysAgo(now, days) {
  const d = startOfDay(now);
  d.setDate(d.getDate() - days);
  return d;
}

// "2026-09-20" -> local midnight of that day (not UTC midnight, which would
// shift the boundary by the viewer's timezone offset).
function parseLocalDate(value) {
  if (!value) return null;
  const [y, m, d] = value.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

// Local-time [from, to] for the chosen date filter; either end may be null
// (open-ended, e.g. "today" has no upper bound so live events still match).
export function dateRangeFor(filters, now = new Date()) {
  switch (filters.datePreset) {
    case "today":
      return { from: startOfDay(now), to: null };
    case "yesterday":
      return { from: daysAgo(now, 1), to: new Date(startOfDay(now).getTime() - 1) };
    case "last7":
      return { from: daysAgo(now, 6), to: null };
    case "last30":
      return { from: daysAgo(now, 29), to: null };
    case "custom": {
      const from = parseLocalDate(filters.customFrom);
      const toDay = parseLocalDate(filters.customTo);
      // Inclusive of the whole "to" day.
      const to = toDay ? new Date(toDay.getFullYear(), toDay.getMonth(), toDay.getDate(), 23, 59, 59, 999) : null;
      return { from, to };
    }
    default:
      return { from: null, to: null };
  }
}

// Query params for GET /events.
export function toQueryParams(filters, now = new Date()) {
  const { from, to } = dateRangeFor(filters, now);
  return {
    camera: filters.camera || undefined,
    eventType: filters.eventType || undefined,
    severity: filters.severity || undefined,
    dateFrom: from ? from.toISOString() : undefined,
    dateTo: to ? to.toISOString() : undefined,
  };
}

// Does a live-pushed event belong in the currently filtered list?
export function eventMatchesFilters(event, filters, now = new Date()) {
  if (filters.camera && event.cameraId !== filters.camera) return false;
  if (filters.eventType && event.event !== filters.eventType) return false;
  if (filters.severity && event.severity !== filters.severity) return false;
  const { from, to } = dateRangeFor(filters, now);
  const time = new Date(event.time).getTime();
  if (from && time < from.getTime()) return false;
  if (to && time > to.getTime()) return false;
  return true;
}

export function hasActiveFilters(filters) {
  return Boolean(filters.camera || filters.eventType || filters.severity || filters.datePreset !== "all");
}

// A short, filename-safe description of the active filters for exports.
export function filtersFileLabel(filters, cameraName) {
  const parts = [];
  if (filters.camera) parts.push(cameraName || filters.camera);
  if (filters.eventType) parts.push(filters.eventType);
  if (filters.severity) parts.push(filters.severity);
  if (filters.datePreset === "custom") {
    parts.push([filters.customFrom, filters.customTo].filter(Boolean).join("_to_") || "custom-dates");
  } else if (filters.datePreset !== "all") {
    parts.push(filters.datePreset);
  }
  return parts
    .join("-")
    .replace(/[^A-Za-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
}
