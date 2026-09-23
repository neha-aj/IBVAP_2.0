import { api } from "./api";
import { accessToken } from "../utils/accessToken";

export const authService = {
  // M25 MFA: `totpCode` is omitted entirely for an account that hasn't
  // enabled MFA (the backend field is optional/ignored in that case) --
  // this call shape is unchanged for every existing caller that doesn't
  // pass one.
  //
  // M25 hardening: the backend no longer returns a refresh token in this
  // response at all -- it sets it as an httpOnly cookie instead (api.js's
  // `credentials: "include"` is what lets the browser receive/send it).
  // Only the access token is ours to hold, and only in memory.
  async login(username, password, totpCode) {
    const body = totpCode ? { username, password, totpCode } : { username, password };
    const data = await api.post("/auth/login", body);
    accessToken.set(data.accessToken);
    return data.user;
  },

  async logout() {
    try {
      // No body needed -- the backend reads/revokes the refresh token from
      // the httpOnly cookie itself (sent automatically) and clears it.
      await api.post("/auth/logout");
    } finally {
      accessToken.clear();
    }
  },

  me: () => api.get("/auth/me"),

  isAuthenticated: () => Boolean(accessToken.get()),

  // M25 MFA management -- called from Settings, not the login form.
  mfa: {
    status: () => api.get("/auth/mfa/status"),
    enroll: () => api.post("/auth/mfa/enroll"),
    verify: (code) => api.post("/auth/mfa/verify", { code }),
    disable: () => api.post("/auth/mfa/disable"),
  },
};
