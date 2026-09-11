import { Clock3, MapPin, Video } from "lucide-react";
import Badge from "../common/Badge";

export default function EvidenceCard({ evidence, selected, onSelect }) {
  return (
    <article
      onClick={() => onSelect(evidence)}
      className={`cursor-pointer border bg-panel p-4 transition-colors hover:border-secondary ${
        selected ? "border-info ring-1 ring-info" : "border-line"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0 text-info">
          <Video size={17} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={evidence.severity}>{evidence.severity}</Badge>
          </div>

          <h3 className="mt-2 text-sm font-semibold text-primary">
            {evidence.event}
          </h3>

          <p className="mt-1 text-[11px] font-medium text-secondary">
            {evidence.cameraName}
          </p>

          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-muted">
            <span className="flex items-center gap-1">
              <MapPin size={12} />
              {evidence.location || "Unknown location"}
            </span>

            <span className="flex items-center gap-1">
              <Clock3 size={12} />
              {new Date(evidence.time).toLocaleString([], {
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
