import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { authService } from "../../services/authService";

// M25 MFA: lets the signed-in user enroll/verify/disable TOTP-based
// two-factor auth on their own account. No QR-code rendering here (keeps
// this change free of a new frontend library) -- the secret is shown as
// text for manual entry into an authenticator app.
export default function MfaSettingsPanel() {
  const [status, setStatus] = useState(null); // { enabled } | null while loading
  const [loadError, setLoadError] = useState(null);

  const [enrollment, setEnrollment] = useState(null); // { secret, provisioningUri } while mid-enrollment
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  const load = useCallback(async () => {
    try {
      setStatus(await authService.mfa.status());
      setLoadError(null);
    } catch (err) {
      setLoadError(err);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleEnroll() {
    setBusy(true);
    setActionError(null);
    try {
      setEnrollment(await authService.mfa.enroll());
      setCode("");
    } catch (err) {
      setActionError(err.detail || err.message || "Couldn't start enrollment.");
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify(e) {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      await authService.mfa.verify(code);
      setEnrollment(null);
      setCode("");
      await load();
    } catch (err) {
      setActionError(err.detail || err.message || "Invalid code.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisable() {
    setBusy(true);
    setActionError(null);
    try {
      await authService.mfa.disable();
      await load();
    } catch (err) {
      setActionError(err.detail || err.message || "Couldn't disable MFA.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel mb-5">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <ShieldCheck size={15} className="text-info" />
        <h2 className="font-semibold">Two-Factor Authentication</h2>
      </div>

      <div className="p-4">
        {loadError ? (
          <p className="text-xs text-danger">Couldn't load your MFA status.</p>
        ) : status === null ? (
          <p className="text-xs text-muted">Loading...</p>
        ) : enrollment ? (
          <form onSubmit={handleVerify} className="space-y-3">
            <p className="text-xs leading-5 text-secondary">
              Add this key to an authenticator app (Google Authenticator, Authy, 1Password, ...), then enter the
              6-digit code it shows to finish turning on two-factor authentication.
            </p>
            <div className="border border-line bg-panelSecondary p-3">
              <p className="text-[9px] font-bold uppercase tracking-wider text-muted">Setup Key</p>
              <p className="mt-1 break-all font-mono text-xs text-primary">{enrollment.secret}</p>
            </div>
            <label className="block text-xs text-secondary">
              Authenticator Code
              <input
                autoFocus
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className="mt-1 w-full max-w-40 border border-line bg-panelSecondary px-3 py-2 text-xs tracking-[.3em] text-primary outline-none focus:border-info"
                placeholder="000000"
                autoComplete="one-time-code"
              />
            </label>
            {actionError && <p className="text-xs text-danger">{actionError}</p>}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={busy || code.length !== 6}
                className="border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "Verifying..." : "Confirm and Enable"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEnrollment(null);
                  setActionError(null);
                }}
                className="border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:text-primary"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : status.enabled ? (
          <div>
            <p className="text-xs leading-5 text-secondary">
              Two-factor authentication is <span className="font-semibold text-success">enabled</span> on your
              account. You'll be asked for a code from your authenticator app each time you sign in.
            </p>
            {actionError && <p className="mt-3 text-xs text-danger">{actionError}</p>}
            <button
              type="button"
              onClick={handleDisable}
              disabled={busy}
              className="mt-4 border border-danger/40 bg-danger/10 px-3 py-2 text-xs font-semibold text-danger hover:bg-danger/15 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Disabling..." : "Disable Two-Factor Authentication"}
            </button>
          </div>
        ) : (
          <div>
            <p className="text-xs leading-5 text-secondary">
              Two-factor authentication is <span className="font-semibold text-muted">not enabled</span>. Turn it on
              to require a code from an authenticator app in addition to your password when signing in.
            </p>
            {actionError && <p className="mt-3 text-xs text-danger">{actionError}</p>}
            <button
              type="button"
              onClick={handleEnroll}
              disabled={busy}
              className="mt-4 border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? "Starting..." : "Enable Two-Factor Authentication"}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
