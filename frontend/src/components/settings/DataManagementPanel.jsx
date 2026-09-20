import { useCallback, useEffect, useState } from "react";
import { Database, RefreshCw, Trash2, TriangleAlert, X } from "lucide-react";
import { dataService } from "../../services/dataService";
import { alertService } from "../../services/alertService";
import { useAlerts } from "../../hooks/useAlerts";
import { useAuth } from "../../hooks/useAuth";

const CONFIRMATION_WORD = "RESET";
const POLL_IDLE_MS = 30000;
const POLL_BUSY_MS = 2000;

const SCOPES = [
  // The gentle option: frees most of the disk (Direction Observed events are the bulk of
  // stored images) without deleting a single event or alert.
  { value: "direction", label: "Direction Observed images only (keep all events & alerts)", days: null, only: "direction_images" },
  { value: "all", label: "Everything (events, alerts and all evidence)", days: null },
  { value: "1", label: "Older than 1 day", days: 1 },
  { value: "7", label: "Older than 7 days", days: 7 },
  { value: "30", label: "Older than 30 days", days: 30 },
  { value: "90", label: "Older than 90 days", days: 90 },
];

function formatBytes(bytes) {
  if (!bytes) return "0 MB";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value >= 100 || i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`;
}

const n = (value) => (value === null || value === undefined ? "—" : value.toLocaleString());

// Manual release valve for the Events / Alerts data. Nothing in the system
// deletes events, alerts or their evidence automatically, and each event keeps
// a snapshot image (critical ones a video clip too), so on busy cameras this
// grows without limit -- this shows what's stored and lets an administrator
// clear all of it, or just what's older than N days.
export default function DataManagementPanel() {
  const { user } = useAuth();
  const { setAlerts } = useAlerts();
  const isAdmin = user?.role === "admin";

  const [summary, setSummary] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [scope, setScope] = useState("direction");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resetError, setResetError] = useState(null);
  const [lastReset, setLastReset] = useState(null);

  const load = useCallback(async () => {
    try {
      setSummary(await dataService.getSummary());
      setLoadError(null);
    } catch (err) {
      setLoadError(err);
    }
  }, []);

  const cleanupStatus = summary?.cleanup?.status;

  useEffect(() => {
    load();
    const timer = setInterval(load, cleanupStatus === "running" ? POLL_BUSY_MS : POLL_IDLE_MS);
    return () => clearInterval(timer);
  }, [load, cleanupStatus]);

  const selectedScope = SCOPES.find((s) => s.value === scope) || SCOPES[0];

  async function handleReset() {
    setSubmitting(true);
    setResetError(null);
    try {
      const result = await dataService.reset({ olderThanDays: selectedScope.days, only: selectedScope.only, confirm: typed });
      setLastReset({ ...result, scopeLabel: selectedScope.label, only: selectedScope.only });
      setConfirmOpen(false);
      setTyped("");
      await load();
      // The Alerts page's shared list is held in memory -- refresh it so it
      // doesn't keep showing rows that no longer exist.
      alertService.getAll().then(setAlerts).catch(() => setAlerts([]));
    } catch (err) {
      setResetError(err.detail || err.message || "The reset failed. Nothing was deleted.");
    } finally {
      setSubmitting(false);
    }
  }

  const cleanup = summary?.cleanup;
  const running = cleanup?.status === "running";

  return (
    <section className="panel mb-5">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Database size={15} className="text-info" />
          <h2 className="font-semibold">Data Management</h2>
        </div>
        <button
          type="button"
          onClick={load}
          className="flex items-center gap-1.5 text-[11px] font-semibold text-secondary hover:text-primary"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      <div className="p-4">
        <p className="text-xs leading-5 text-secondary">
          Events, alerts and their evidence (a snapshot image per event, plus a video clip for critical ones) are kept
          until you remove them — nothing is deleted automatically, so on busy cameras this grows continuously and can
          eventually fill the disk and slow everything down. Use this to clear it out.
        </p>

        {loadError ? (
          <p className="mt-4 text-xs text-danger">Couldn't load the current data totals.</p>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Stat label="Events" value={n(summary?.events)} />
            <Stat label="Alerts" value={n(summary?.alerts)} />
            <Stat label="Evidence images" value={n(summary?.snapshots)} />
            <Stat label="Evidence clips" value={n(summary?.recordings)} />
            <Stat label="Direction Observed images" value={n(summary?.directionImages)} />
          </div>
        )}
        {summary?.oldestEventAt && (
          <p className="mt-2 text-[11px] text-muted">
            Oldest stored event: {new Date(summary.oldestEventAt).toLocaleString()}
          </p>
        )}

        {running && (
          <div role="status" className="mt-4 border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            {cleanup.snapshotsTotal > 0
              ? `Removing Direction Observed images: ${cleanup.snapshotsRemoved.toLocaleString()} of ${cleanup.snapshotsTotal.toLocaleString()}… `
              : "Removing evidence files in the background… "}
            This can take a few minutes for a large backlog. You can leave this page.
          </div>
        )}
        {!running && lastReset?.only && cleanup?.status === "done" && (
          <div role="status" className="mt-4 border border-success/40 bg-success/10 px-3 py-2 text-xs text-success">
            Done: removed {cleanup.snapshotsRemoved.toLocaleString()} Direction Observed images —{" "}
            {formatBytes(cleanup.bytesFreed)} freed. All events and alerts were kept.
          </div>
        )}
        {!running && lastReset && !lastReset.only && cleanup?.status === "done" && (
          <div role="status" className="mt-4 border border-success/40 bg-success/10 px-3 py-2 text-xs text-success">
            Done ({lastReset.scopeLabel.toLowerCase()}): removed {lastReset.eventsRemoved.toLocaleString()} events and{" "}
            {lastReset.alertsRemoved.toLocaleString()} alerts, {cleanup.snapshotsRemoved.toLocaleString()} images and{" "}
            {cleanup.recordingsRemoved.toLocaleString()} clips — {formatBytes(cleanup.bytesFreed)} freed.
          </div>
        )}
        {cleanup?.status === "failed" && (
          <div role="alert" className="mt-4 border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
            {lastReset?.only ? "Removing the images stopped part-way" : "Events and alerts were cleared, but removing the evidence files failed"}{" "}
            ({cleanup.error || "unknown error"}). Run it again to finish — it picks up where it left off.
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-end gap-3 border-t pt-4">
          <label className="text-xs text-muted">
            What to remove
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              disabled={running || !isAdmin}
              className="mt-1 block min-w-48 rounded-sm border border-line bg-[#0b141c] p-2 text-slate-300 outline-none focus:border-info disabled:opacity-50"
            >
              {SCOPES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={() => {
              setResetError(null);
              setTyped("");
              setConfirmOpen(true);
            }}
            disabled={running || !isAdmin}
            className="flex items-center gap-2 border border-danger/40 bg-danger/10 px-3 py-2 text-xs font-semibold text-danger hover:bg-danger/15 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Trash2 size={13} />
            Reset data…
          </button>

          {!isAdmin && <p className="text-[11px] text-muted">Only administrators can reset data.</p>}
        </div>
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="panel w-full max-w-md overflow-hidden">
            <div className="flex items-start justify-between border-b border-line p-4">
              <div className="flex items-start gap-3">
                <div className="border border-danger/40 bg-danger/10 p-2 text-danger">
                  <TriangleAlert size={17} />
                </div>
                <div>
                  <p className="eyebrow">Confirm</p>
                  <h2 className="mt-1 text-sm font-semibold text-primary">
                    {selectedScope.only ? "Permanently delete Direction Observed images" : `Permanently delete: ${selectedScope.label.toLowerCase()}`}
                  </h2>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
                aria-label="Cancel"
              >
                <X size={17} />
              </button>
            </div>

            <div className="space-y-3 p-4 text-xs leading-5 text-secondary">
              {selectedScope.only ? (
                <>
                  <p>
                    This deletes the saved snapshot image of every Direction Observed event. It cannot be undone.
                  </p>
                  <p className="text-muted">
                    Kept: every event and alert (Direction Observed events stay in the list, just without a picture),
                    all other snapshots, and all video clips.
                  </p>
                </>
              ) : (
                <>
                  <p>
                    This deletes {selectedScope.days ? `events and alerts older than ${selectedScope.days} day${selectedScope.days === 1 ? "" : "s"}` : "all events and alerts"}
                    , along with their evidence images and video clips. It cannot be undone.
                  </p>
                  <p className="text-muted">
                    Not affected: cameras, zones, settings, users, license-plate reads, person-search data and the
                    tracking history behind the Analytics people/vehicle counts. Analytics charts built from events
                    and alerts update within about a minute.
                  </p>
                </>
              )}
              <label className="block">
                Type <span className="font-mono font-semibold text-primary">{CONFIRMATION_WORD}</span> to confirm
                <input
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  autoFocus
                  className="mt-1 block w-full border border-line bg-panelSecondary px-3 py-2 font-mono text-xs text-primary outline-none focus:border-danger"
                />
              </label>
              {resetError && <p className="text-danger">{resetError}</p>}
            </div>

            <div className="flex justify-end gap-2 border-t border-line p-4">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={typed !== CONFIRMATION_WORD || submitting}
                className="border border-danger/40 bg-danger/10 px-4 py-2 text-xs font-semibold text-danger hover:bg-danger/15 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting ? "Deleting..." : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="border border-line bg-panelSecondary p-3">
      <p className="text-[9px] font-bold uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold text-primary">{value}</p>
    </div>
  );
}
