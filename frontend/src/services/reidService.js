import { api } from "./api";

// Phase 2 M16 (Person Re-ID) + M17 (Vehicle Re-ID, same service/endpoints,
// `objectType` picks which embedding table/model is searched -- defaults
// to "person" server-side too, so passing it is optional here.
export const reidService = {
  searchByTrack: (cameraId, trackId, objectType = "person") =>
    api.post(
      `/reid/search?camera=${encodeURIComponent(cameraId)}&objectType=${objectType}`,
      { trackId }
    ),
  searchByImage: (file, objectType = "person") => {
    const formData = new FormData();
    formData.append("file", file);
    return api.postForm(`/reid/search/upload?objectType=${objectType}`, formData);
  },
  getMatches: (cameraId, personRef, objectType = "person") =>
    api.get("/reid/matches", { camera: cameraId, personRef, objectType }),
};
