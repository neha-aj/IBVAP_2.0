import { Download, MapPin } from "lucide-react";

import Badge from "../common/Badge";
import { GATEWAY_ORIGIN } from "../../services/api";

export default function EvidenceDetail({ evidence }) {
  const exportUrl = evidence?.recordingUrl
    ? `${GATEWAY_ORIGIN}${evidence.recordingUrl}&download=true`
    : undefined;

  return (
    <section className="panel mt-2 overflow-hidden border-info">
      <div className="border-b border-line p-4">
        <p className="eyebrow">Evidence Details</p>

        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone={evidence.severity}>{evidence.severity}</Badge>
        </div>

        <h2 className="mt-3 text-sm font-semibold text-primary">
          {evidence.event}
        </h2>

        <p className="mt-1 font-mono text-[10px] text-muted">
          {evidence.id}
        </p>
      </div>

      <div className="p-4">
        {evidence.recordingUrl ? (
          <video
            key={evidence.recordingUrl}
            controls
            className="w-full border border-line bg-black"
            src={`${GATEWAY_ORIGIN}${evidence.recordingUrl}`}
          />
        ) : (
          <p className="text-xs text-muted">Capturing clip...</p>
        )}
      </div>

      <div className="space-y-4 p-4 pt-0">
        <DetailRow label="Camera" value={evidence.cameraName} />

        <DetailRow
          label="Time"
          value={new Date(evidence.time).toLocaleString()}
        />

        <DetailRow
          label="Location"
          value={
            <span className="flex items-center gap-1">
              <MapPin size={12} className="text-muted" />
              {evidence.location || "Unknown"}
            </span>
          }
        />

        {evidence.objectType && (
          <DetailRow label="Object Type" value={evidence.objectType} />
        )}

        <div>
          <p className="eyebrow">Description</p>
          <p className="mt-2 text-xs leading-5 text-secondary">
            {evidence.description || `${evidence.event} detected on ${evidence.cameraName}.`}
          </p>
        </div>
      </div>

      <div className="border-t border-line p-4">
        <a
          href={exportUrl}
          aria-disabled={!evidence.recordingUrl}
          className={`flex items-center justify-center gap-2 border px-3 py-2 text-xs font-semibold ${
            evidence.recordingUrl
              ? "border-info bg-info/10 text-info hover:bg-info/15"
              : "cursor-not-allowed border-line bg-panelSecondary text-muted"
          }`}
        >
          <Download size={13} />
          Export for Investigation
        </a>
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

      <p className="mt-1 truncate text-xs font-medium text-primary">
        {value}
      </p>
    </div>
  );
}
