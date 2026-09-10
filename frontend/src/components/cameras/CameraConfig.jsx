import {
  Camera,
  CircleDot,
  Cpu,
  Gauge,
  Maximize2,
  Radio,
  ShieldCheck,
  X,
} from "lucide-react";

import Badge from "../common/Badge";

export default function CameraConfig({
  camera,
  onClose,
  onEdit,
  onConfigureDetection,
  onConfigureFence,
  onConfigureCalibration,
}) {
  if (!camera) return null;

  return (  
    <section className="panel mt-5 overflow-hidden">
      <div className="flex items-start justify-between border-b border-line p-4">
        <div>
          <p className="eyebrow">Camera Configuration</p>

          <div className="mt-2 flex items-center gap-2">
            <h2 className="text-sm font-semibold text-primary">
              {camera.name}
            </h2>

            <Badge tone={camera.status}>{camera.status}</Badge>
          </div>

          <p className="mt-1 font-mono text-[10px] text-muted">
            {camera.id}
          </p>
        </div>

        <button
          onClick={onClose}
          className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
          aria-label="Close camera configuration"
        >
          <X size={16} />
        </button>
      </div>

      <div className="grid gap-0 lg:grid-cols-2">
        <div className="border-b border-line p-4 lg:border-r">
          <p className="eyebrow">Device Information</p>

          <div className="mt-4 space-y-3">
            <ConfigRow
              icon={<Camera size={15} />}
              label="Camera Name"
              value={camera.name}
            />

            <ConfigRow
              icon={<Radio size={15} />}
              label="Camera ID"
              value={camera.id}
            />

            <ConfigRow
              icon={<CircleDot size={15} />}
              label="Location"
              value={camera.location}
            />

            <ConfigRow
              icon={<ShieldCheck size={15} />}
              label="Sector"
              value={camera.sector}
            />
          </div>
        </div>

        <div className="border-b border-line p-4">
          <p className="eyebrow">Stream Configuration</p>

          <div className="mt-4 space-y-3">
            <ConfigRow
              icon={<Maximize2 size={15} />}
              label="Resolution"
              value={camera.resolution}
            />

            <ConfigRow
              icon={<Radio size={15} />}
              label="Frame Rate"
              value={`${camera.fps} FPS`}
            />

            <ConfigRow
              icon={<Cpu size={15} />}
              label="Inference"
              value="AI Processing Enabled"
            />

            <ConfigRow
              icon={<ShieldCheck size={15} />}
              label="Last Active"
              value={camera.lastActive}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 p-4">
        <button
          onClick={onEdit}
          className="border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:text-primary"
        >
          Edit Configuration
        </button>

        <button
          onClick={onConfigureDetection}
          className="border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:text-primary">
          Configure Detection
        </button>

        <button onClick={onConfigureFence} className="border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:text-primary">
            Configure Zones &amp; Lines
        </button>

        <button
          onClick={onConfigureCalibration}
          className="flex items-center gap-1.5 border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:text-primary"
        >
          <Gauge size={13} />
          Speed Calibration
        </button>
      </div>
    </section>
  );
}

function ConfigRow({ icon, label, value }) {
  return (
    <div className="flex items-center gap-3 border border-line bg-panelSecondary p-3">
      <div className="text-info">{icon}</div>

      <div className="min-w-0">
        <p className="text-[9px] uppercase tracking-wider text-muted">
          {label}
        </p>

        <p className="mt-1 truncate text-xs font-medium text-primary">
          {value}
        </p>
      </div>
    </div>
  );
}

