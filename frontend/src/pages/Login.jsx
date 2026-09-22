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
  const [totpCode, setTotpCode] = useState("");
  // M25 MFA: set once the backend responds "mfa-required" for a correct
  // username/password -- switches the form to ask for the authenticator
  // code instead of erroring out as a failed login.
  const [needsMfa, setNeedsMfa] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username, password, needsMfa ? totpCode : undefined);
      const redirectTo = location.state?.from?.pathname || "/";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err.type === "https://ibvap.dev/errors/mfa-required") {
        setNeedsMfa(true);
        setError("");
      } else if (needsMfa) {
        setError("Invalid authenticator code.");
      } else {
        setError(err.status === 401 ? "Invalid username or password." : err.message || "Login failed.");
      }
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
                autoFocus={!needsMfa}
                disabled={needsMfa}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1 w-full border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info disabled:opacity-50"
                placeholder="admin"
                autoComplete="username"
              />
            </label>

            <label className="block text-xs text-secondary">
              Password
              <input
                type="password"
                disabled={needsMfa}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info disabled:opacity-50"
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </label>

            {needsMfa && (
              <label className="block text-xs text-secondary">
                Authenticator Code
                <input
                  autoFocus
                  inputMode="numeric"
                  maxLength={6}
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                  className="mt-1 w-full border border-line bg-panelSecondary px-3 py-2 text-xs tracking-[.3em] text-primary outline-none placeholder:text-muted focus:border-info"
                  placeholder="000000"
                  autoComplete="one-time-code"
                />
              </label>
            )}
          </div>

          {error && <p className="mt-3 text-xs text-danger">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !username || !password || (needsMfa && totpCode.length !== 6)}
            className="mt-5 w-full border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Signing in..." : needsMfa ? "Verify Code" : "Sign In"}
          </button>

          {needsMfa && (
            <button
              type="button"
              onClick={() => {
                setNeedsMfa(false);
                setTotpCode("");
                setError("");
              }}
              className="mt-2 w-full text-center text-[10px] text-muted hover:text-secondary"
            >
              Back
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
