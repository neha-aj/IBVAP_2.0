import { api } from "./api";

export const eventService = {
  getAll: async (params) => {
    const data = await api.get("/events", params);
    return data.items;
  },
  getById: (id) => api.get(`/events/${id}`),
  updateStatus: (id, status) => api.patch(`/events/${id}`, { status }),
};
