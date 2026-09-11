import { GATEWAY_ORIGIN } from "../../services/api";
import Badge from "../common/Badge";

export default function AlertDetails({
  alert,
  onAcknowledge,
  onResolve,
  onViewCamera,
}) {
  return (
    <section className="panel mt-2 overflow-hidden border-info">
      <div className="border-b border-line p-4">
        <p className="eyebrow">Alert Details</p>

        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone={alert.severity}>{alert.severity}</Badge>
          <Badge tone={alert.status}>{alert.status === "reviewing" ? "acknowledged" : alert.status}</Badge>
        </div>

        <h2 className="mt-3 text-sm font-semibold text-primary">
          {alert.type}
        </h2>

        <p className="mt-1 font-mono text-[10px] text-muted">
          {alert.id}
        </p>
      </div>

      <div className="space-y-4 p-4">
        <DetailRow label="Camera" value={alert.cameraName} />
        <DetailRow label="Camera ID" value={alert.cameraId} />
        <DetailRow label="Location" value={alert.location} />
        <DetailRow
          label="Detected At"
          value={new Date(alert.timestamp).toLocaleString()}
        />

        {alert.objectType && (
          <DetailRow label="Object Type" value={alert.objectType} />
        )}

        <div>
          <p className="eyebrow">Description</p>
          <p className="mt-2 text-xs leading-5 text-secondary">
            {alert.description || `${alert.type} detected on ${alert.cameraName}.`}
          </p>
        </div>

        {alert.severity === "critical" && (
          <div>
            <p className="eyebrow">Recording</p>
            {alert.recordingUrl ? (
              <video
                key={alert.recordingUrl}
                controls
                className="mt-2 w-full border border-line bg-black"
                src={`${GATEWAY_ORIGIN}${alert.recordingUrl}`}
              />
            ) : (
              <p className="mt-2 text-xs text-muted">Capturing clip...</p>
            )}
          </div>
        )}
      </div>

      <div className="flex gap-2 border-t border-line p-4">
        <button
          onClick={onViewCamera}
          className="flex-1 border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15"
        >
          View Camera
        </button>

        {alert.status === "active" && (
          <button
            onClick={onAcknowledge}
            className="flex-1 border border-warning bg-warning/10 px-3 py-2 text-xs font-semibold text-warning hover:bg-warning/15"
          >
            Acknowledge
          </button>
        )}

        {alert.status !== "resolved" && (
          <button
            onClick={onResolve}
            className="flex-1 border border-success bg-success/10 px-3 py-2 text-xs font-semibold text-success hover:bg-success/15"
          >
            Resolve
          </button>
        )}
      </div>
    </section>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="border border-line bg-panelSecondary p-3">
      <p className="text-[9px] font-bold uppercase tracking-wider text-muted">
        {label}
      </p>

      <p className="mt-1 text-xs font-medium text-primary">
        {value}
      </p>
    </div>
  );
}
