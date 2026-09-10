import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "../hooks/useAuth";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username, password);
      const redirectTo = location.state?.from?.pathname || "/";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.status === 401 ? "Invalid username or password." : err.message || "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-ink px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <ShieldCheck size={28} className="text-info" />
          <p className="mt-3 text-xl font-bold tracking-[.08em] text-primary">IBVAP</p>
          <p className="mt-1 text-[10px] uppercase tracking-[.14em] text-secondary">
            Intelligent Border Video Analytics Platform
          </p>
        </div>

        <form onSubmit={handleSubmit} className="panel p-5">
          <p className="eyebrow">Sign in</p>

          <div className="mt-4 space-y-3">
            <label className="block text-xs text-secondary">
              Username
              <input
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1 w-full border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
                placeholder="admin"
                autoComplete="username"
              />
            </label>

            <label className="block text-xs text-secondary">
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </label>
          </div>

          {error && <p className="mt-3 text-xs text-danger">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !username || !password}
            className="mt-5 w-full border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
