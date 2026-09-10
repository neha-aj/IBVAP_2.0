import { api } from "./api";

export const zoneService = {
  getZones: (cameraId) => api.get(`/cameras/${cameraId}/zones`),
  createZone: (cameraId, payload) => api.post(`/cameras/${cameraId}/zones`, payload),
  updateZone: (cameraId, zoneId, payload) => api.put(`/cameras/${cameraId}/zones/${zoneId}`, payload),
  deleteZone: (cameraId, zoneId) => api.delete(`/cameras/${cameraId}/zones/${zoneId}`),

  getZoneLines: (cameraId) => api.get(`/cameras/${cameraId}/zone-lines`),
  createZoneLine: (cameraId, payload) => api.post(`/cameras/${cameraId}/zone-lines`, payload),
  updateZoneLine: (cameraId, lineId, payload) => api.put(`/cameras/${cameraId}/zone-lines/${lineId}`, payload),
  deleteZoneLine: (cameraId, lineId) => api.delete(`/cameras/${cameraId}/zone-lines/${lineId}`),
};
