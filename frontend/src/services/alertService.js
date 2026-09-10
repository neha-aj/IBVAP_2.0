import { api } from "./api";

export const alertService = {
  getAll: async (params) => {
    const data = await api.get("/alerts", params);
    return data.items;
  },
  getById: (id) => api.get(`/alerts/${id}`),
  // Real backend status enum is active|reviewing|resolved (event-alert
  // Alert model) -- there is no "acknowledged" status server-side.
  updateStatus: (id, status) => api.patch(`/alerts/${id}/status`, { status }),
};
