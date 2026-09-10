import { api } from "./api";

export const systemService = {
  getHealth: () => api.get("/system/health"),
};
