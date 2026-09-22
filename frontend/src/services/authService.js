import { api } from "./api";
import { tokenStorage } from "../utils/tokenStorage";

export const authService = {
  // M25 MFA: `totpCode` is omitted entirely for an account that hasn't
  // enabled MFA (the backend field is optional/ignored in that case) --
  // this call shape is unchanged for every existing caller that doesn't
  // pass one.
  async login(username, password, totpCode) {
    const body = totpCode ? { username, password, totpCode } : { username, password };
    const data = await api.post("/auth/login", body);
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

  // M25 MFA management -- called from Settings, not the login form.
  mfa: {
    status: () => api.get("/auth/mfa/status"),
    enroll: () => api.post("/auth/mfa/enroll"),
    verify: (code) => api.post("/auth/mfa/verify", { code }),
    disable: () => api.post("/auth/mfa/disable"),
  },
};
