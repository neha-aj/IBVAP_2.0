import { api } from "./api";

export const cameraService = {
  // API Spec §2: response is an envelope {items,total,page,pageSize} --
  // callers of getAll only ever need the array itself.
  getAll: async (params) => {
    const data = await api.get("/cameras", params);
    return data.items;
  },
  getById: (id) => api.get(`/cameras/${id}`),
  update: (id, payload) => api.put(`/cameras/${id}`, payload),
  getStatusSummary: () => api.get("/cameras/status/summary"),
  // modality: undefined (default RGB) or "thermal" -- only meaningful for a
  // 'dual' camera's second stream (M11); every other camera type omits it.
  getStream: (id, modality) => api.get(`/cameras/${id}/stream${modality ? `?modality=${modality}` : ""}`),
  // Pause = freeze the live view AND stop all analysis for that camera (the
  // backend stops feeding its frames into the detection pipeline). Needs the
  // operator role or higher.
  getPaused: () => api.get("/cameras/paused"),
  pause: (id) => api.post(`/cameras/${id}/pause`),
  resume: (id) => api.post(`/cameras/${id}/resume`),
  // Adds a simulated thermal view rendered from this camera's own uploaded
  // video (no separate thermal file); detection then runs on both views
  // and counts each object once. Admin only.
  generateThermal: (id) => api.post(`/cameras/${id}/thermal/generate`),
  removeGeneratedThermal: (id) => api.delete(`/cameras/${id}/thermal/generate`),
  getCurrentDetections: (id) => api.get(`/cameras/${id}/detections/current`),
  getHealth: (id) => api.get(`/cameras/${id}/health`),
  create: (payload) => api.post("/cameras", payload),
  delete: (id) => api.delete(`/cameras/${id}`),
  // slot: "rgb" (default) or "thermal" -- only meaningful for a 'dual'
  // camera's second stream (M11); every other camera type just omits it.
  uploadVideo: (id, file, slot) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.postForm(`/cameras/${id}/upload${slot ? `?slot=${slot}` : ""}`, formData);
  },
};
