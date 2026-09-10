import { api } from "./api";

export const analyticsService = {
  getDashboardStats: () => api.get("/dashboard/stats"),
  getActivityOverview: (range = "today") => api.get("/analytics/activity-overview", { range }),
  getActivityWeekly: () => api.get("/analytics/activity-weekly"),
  getAlertsByType: () => api.get("/analytics/alerts-by-type"),
  getCameraUptime: () => api.get("/analytics/camera-uptime"),
  getEventsByCamera: () => api.get("/analytics/events-by-camera"),
  getPpeCompliance: () => api.get("/analytics/ppe-compliance"),
  getDirectionFlow: (camera) => api.get("/analytics/direction-flow", camera ? { camera } : {}),
  getPeopleVehiclesByCamera: () => api.get("/analytics/people-vehicles-by-camera"),
};
