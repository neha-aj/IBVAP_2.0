// M25 hardening: the access token now lives only in memory, never in
// localStorage -- an XSS bug reading localStorage could otherwise
// exfiltrate it directly. The tradeoff is a fresh page load starts with
// no token (memory is gone), so AuthContext does a silent refresh (via
// the httpOnly refresh cookie -- see authService.js) on every app start
// to get a new one before rendering anything that needs it.
let currentToken = null;

export const accessToken = {
  get: () => currentToken,
  set: (token) => {
    currentToken = token;
  },
  clear: () => {
    currentToken = null;
  },
};
