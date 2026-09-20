import { api } from "./api";

// Server-side cap for one page (see event-alert-service's list_events) and how
// many rows an export will pull in total -- a bound so a huge history can't
// hang the tab; the export tells the user when it was hit.
const EXPORT_PAGE_SIZE = 1000;
export const EXPORT_MAX_ROWS = 10000;

export const eventService = {
  getAll: async (params) => {
    const data = await api.get("/events", params);
    return data.items;
  },
  // Same endpoint, but keeping the {items,total,page,pageSize} envelope --
  // the Events page needs `total` to say how many events match its filters.
  getPage: (params) => api.get("/events", params),
  // Only the cameras / event types / severities that actually occur in the
  // stored events, with counts -- the Events page's dropdown choices.
  getFilterOptions: () => api.get("/events/filter-options"),
  // Every event matching `params`, newest first, up to `max` rows -- for
  // export. Returns { items, total, truncated }.
  getAllMatching: async (params, { max = EXPORT_MAX_ROWS, onProgress } = {}) => {
    const items = [];
    let total = 0;
    for (let page = 1; items.length < max; page += 1) {
      const data = await api.get("/events", { ...params, page, pageSize: EXPORT_PAGE_SIZE });
      total = data.total;
      items.push(...data.items);
      if (onProgress) onProgress(Math.min(items.length, total), total);
      if (data.items.length < EXPORT_PAGE_SIZE || items.length >= total) break;
    }
    return { items: items.slice(0, max), total, truncated: total > max };
  },
  getById: (id) => api.get(`/events/${id}`),
  updateStatus: (id, status) => api.patch(`/events/${id}`, { status }),
};
