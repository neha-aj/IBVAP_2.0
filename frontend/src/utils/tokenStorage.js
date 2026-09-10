// Persists the JWT pair across page reloads. localStorage (not memory-only)
// so a refresh doesn't force a re-login -- session lifetime is bounded by
// the refresh token's own server-side expiry (API Spec §1) regardless.
const ACCESS_KEY = "ibvap_access_token";
const REFRESH_KEY = "ibvap_refresh_token";

export const tokenStorage = {
  getAccessToken: () => localStorage.getItem(ACCESS_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_KEY),
  setTokens: ({ accessToken, refreshToken }) => {
    if (accessToken) localStorage.setItem(ACCESS_KEY, accessToken);
    if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};
