import { api } from "./api";

// Phase 2 M15 (ANPR Service). `getReads` mirrors cameraService.getAll's
// envelope-unwrapping convention (API returns {items,total,page,pageSize}).
export const anprService = {
  getReads: (params) => api.get("/anpr/reads", params),
  getWatchlist: () => api.get("/anpr/watchlist"),
  addWatchlistEntry: (payload) => api.post("/anpr/watchlist", payload),
  deleteWatchlistEntry: (id) => api.delete(`/anpr/watchlist/${id}`),
};
