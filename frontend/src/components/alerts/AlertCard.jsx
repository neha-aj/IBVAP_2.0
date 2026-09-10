import {
  AlertTriangle,
  CarFront,
  Clock3,
  MapPin,
  UserRound,
} from "lucide-react";

import Badge from "../common/Badge";

const severityIcons = {
  critical: AlertTriangle,
  high: AlertTriangle,
  medium: CarFront,
  low: UserRound,
};

const severityLabels = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export default function AlertCard({ alert, selected, onSelect }) {
  const Icon = severityIcons[alert.severity] || AlertTriangle;

  return (
    <article
      onClick={() => onSelect(alert)}
      className={`cursor-pointer border bg-panel p-4 transition-colors hover:border-secondary ${
        selected ? "border-info ring-1 ring-info" : "border-line"
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 shrink-0 ${
            alert.severity === "critical" || alert.severity === "high"
              ? "text-danger"
              : alert.severity === "medium"
                ? "text-warning"
                : "text-info"
          }`}
        >
          <Icon size={17} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={alert.severity}>
              {severityLabels[alert.severity]}
            </Badge>

            <Badge tone={alert.status}>{alert.status === "reviewing" ? "acknowledged" : alert.status}</Badge>
          </div>

          <h3 className="mt-2 text-sm font-semibold text-primary">
            {alert.type}
          </h3>

          <p className="mt-1 text-[11px] leading-4 text-secondary">
            {alert.description}
          </p>

          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-muted">
            <span className="flex items-center gap-1">
              <MapPin size={12} />
              {alert.location}
            </span>

            <span className="flex items-center gap-1">
              <Clock3 size={12} />
              {new Date(alert.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
          </div>
        </div>
      </div>
    </article>
  );
}