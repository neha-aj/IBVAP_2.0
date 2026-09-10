import { createContext, useCallback, useEffect, useState } from "react";
import { authService } from "../services/authService";
import { tokenStorage } from "../utils/tokenStorage";
import { socket } from "../services/socket";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "loading" while we validate a persisted token on first load, so
  // ProtectedRoute doesn't flash a redirect to /login before that check
  // resolves.
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (!tokenStorage.getAccessToken()) {
        setStatus("unauthenticated");
        return;
      }
      try {
        const me = await authService.me();
        if (cancelled) return;
        setUser(me);
        setStatus("authenticated");
      } catch {
        if (cancelled) return;
        tokenStorage.clear();
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

  const login = useCallback(async (username, password) => {
    const loggedInUser = await authService.login(username, password);
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
