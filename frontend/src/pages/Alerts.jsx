import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCircle2, ShieldAlert } from "lucide-react";

import PageHeader from "../components/layout/PageHeader";
import AlertList from "../components/alerts/AlertList";
import { useAlerts } from "../hooks/useAlerts";
import { alertService } from "../services/alertService";

export default function Alerts() {
  const { alerts, setAlerts, isLoading, error } = useAlerts();
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [status, setStatus] = useState("all");

  const [selectedAlert, setSelectedAlert] = useState(null);

  // Phase 2 M23: a recording clip can attach to an alert seconds after it
  // first appears (background post-roll capture, see event-alert-service's
  // pubsub_publisher.py) -- `alert.updated` already refreshes the `alerts`
  // list live, but `selectedAlert` is a separate snapshot taken at click
  // time, so without this it'd never pick up the recording once it lands.
  useEffect(() => {
    if (!selectedAlert) return;
    const current = alerts.find((a) => a.id === selectedAlert.id);
    if (current && current !== selectedAlert) setSelectedAlert(current);
  }, [alerts, selectedAlert]);

  const filteredAlerts = useMemo(() => {
    const query = search.toLowerCase();

    return alerts.filter((alert) => {
      const matchesSearch =
        alert.id.toLowerCase().includes(query) ||
        alert.type.toLowerCase().includes(query) ||
        alert.cameraName.toLowerCase().includes(query) ||
        (alert.location || "").toLowerCase().includes(query);

      const matchesSeverity =
        severity === "all" || alert.severity === severity;

      const matchesStatus =
        status === "all" || alert.status === status;

      return matchesSearch && matchesSeverity && matchesStatus;
    });
  }, [alerts, search, severity, status]);

  async function updateSelectedAlertStatus(nextStatus) {
    if (!selectedAlert) return;
    const updated = await alertService.updateStatus(selectedAlert.id, nextStatus);
    setAlerts((current) => current.map((alert) => (alert.id === updated.id ? updated : alert)));
    setSelectedAlert(updated);
  }

  const activeCount = alerts.filter((alert) => alert.status === "active").length;

  const criticalCount = alerts.filter(
    (alert) => alert.severity === "critical" && alert.status !== "resolved"
  ).length;

  // Backend status enum is active|reviewing|resolved (no "acknowledged") --
  // the UI keeps the "Acknowledge" button label but tracks the real
  // "reviewing" status underneath.
  const acknowledgedCount = alerts.filter((alert) => alert.status === "reviewing").length;

  return (
    <div>
      <PageHeader
        title="Alert Center"
        subtitle="Real-time security events requiring operator attention"
      />

      {/* Summary */}
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <SummaryCard
          icon={<Bell size={16} />}
          label="Active Alerts"
          value={activeCount}
          tone="danger"
        />

        <SummaryCard
          icon={<ShieldAlert size={16} />}
          label="Critical"
          value={criticalCount}
          tone="warning"
        />

        <SummaryCard
          icon={<CheckCircle2 size={16} />}
          label="Acknowledged"
          value={acknowledgedCount}
          tone="info"
        />
      </div>

      {/* Filters */}
      <section className="panel mb-5 flex flex-wrap items-center gap-3 p-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search alerts..."
          className="min-w-52 flex-1 border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
        />

        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="border border-line bg-panelSecondary p-2 text-xs text-secondary outline-none focus:border-info"
        >
          <option value="all">All severity</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="border border-line bg-panelSecondary p-2 text-xs text-secondary outline-none focus:border-info"
        >
          <option value="all">All status</option>
          <option value="active">Active</option>
          <option value="reviewing">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
      </section>

      {/* Content */}
      {isLoading ? (
        <div className="panel p-10 text-center text-xs text-muted">Loading alerts...</div>
      ) : error ? (
        <div className="panel p-10 text-center text-xs text-danger">Failed to load alerts.</div>
      ) : (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="eyebrow">Security Events</p>
              <p className="mt-1 text-[11px] text-muted">
                Showing {filteredAlerts.length} of {alerts.length} alerts
              </p>
            </div>
          </div>

          <AlertList
            alerts={filteredAlerts}
            selectedAlert={selectedAlert}
            onSelect={setSelectedAlert}
            onAcknowledge={() => updateSelectedAlertStatus("reviewing")}
            onResolve={() => updateSelectedAlertStatus("resolved")}
            onViewCamera={() =>
              selectedAlert && navigate(`/surveillance?camera=${selectedAlert.cameraId}`)
            }
          />
        </div>
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, tone }) {
  const toneClasses = {
    danger: "text-danger",
    warning: "text-warning",
    info: "text-info",
  };

  return (
    <section className="panel p-4">
      <div className="flex items-center gap-2">
        <div className={toneClasses[tone]}>{icon}</div>
        <p className="eyebrow">{label}</p>
      </div>

      <p className="mt-3 text-2xl font-semibold text-primary">{value}</p>
    </section>
  );
}

