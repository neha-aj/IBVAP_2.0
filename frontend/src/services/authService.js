import { api } from "./api";
import { tokenStorage } from "../utils/tokenStorage";

export const authService = {
  async login(username, password) {
    const data = await api.post("/auth/login", { username, password });
    tokenStorage.setTokens({ accessToken: data.accessToken, refreshToken: data.refreshToken });
    return data.user;
  },

  async logout() {
    try {
      await api.post("/auth/logout");
    } finally {
      tokenStorage.clear();
    }
  },

  me: () => api.get("/auth/me"),

  isAuthenticated: () => Boolean(tokenStorage.getAccessToken()),
};
