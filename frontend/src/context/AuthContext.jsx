import { createContext, useCallback, useEffect, useState } from "react";
import { authService } from "../services/authService";
import { accessToken } from "../utils/accessToken";
import { socket } from "../services/socket";
import { refreshAccessToken } from "../services/api";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "loading" while a fresh page load tries to restore a session, so
  // ProtectedRoute doesn't flash a redirect to /login before that check
  // resolves.
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let cancelled = false;

    // M25 hardening: the access token lives only in memory now, so it's
    // always gone after a reload -- there's nothing to "check" the way a
    // localStorage read used to work. Instead, try a silent refresh: if
    // the browser still has a valid httpOnly refresh cookie from a past
    // login, this mints a fresh access token from it with no user-visible
    // prompt; if there's no cookie (or it's expired/revoked), this 401s
    // and the user just sees the login page, same end result as before.
    //
    // Goes through api.js's own de-duplicated `refreshAccessToken` (not a
    // raw fetch) so React's dev-mode double effect invocation can't fire
    // two real concurrent refreshes against a cookie that rotates on use.
    async function restoreSession() {
      try {
        const data = await refreshAccessToken();
        if (cancelled) return;
        setUser(data.user);
        setStatus("authenticated");
      } catch {
        if (cancelled) return;
        accessToken.clear();
        setStatus("unauthenticated");
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Fired by services/api.js when a refresh attempt fails (refresh token
    // itself expired/revoked) -- the request layer has already cleared
    // tokens; this just syncs the auth state so the UI redirects to login.
    function handleAuthExpired() {
      setUser(null);
      setStatus("unauthenticated");
      socket.disconnect();
    }
    window.addEventListener("ibvap:auth-expired", handleAuthExpired);
    return () => window.removeEventListener("ibvap:auth-expired", handleAuthExpired);
  }, []);

  const login = useCallback(async (username, password, totpCode) => {
    const loggedInUser = await authService.login(username, password, totpCode);
    setUser(loggedInUser);
    setStatus("authenticated");
    return loggedInUser;
  }, []);

  const logout = useCallback(async () => {
    await authService.logout();
    setUser(null);
    setStatus("unauthenticated");
    socket.disconnect();
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
