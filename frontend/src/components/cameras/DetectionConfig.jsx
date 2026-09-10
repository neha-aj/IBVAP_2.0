import { useState } from "react";
import { BrainCircuit, X } from "lucide-react";

export default function DetectionConfig({ camera, onClose }) {
  const [config, setConfig] = useState({
    personDetection: true,
    vehicleDetection: true,
    faceDetection: true,
    anpr: true,
    loitering: false,
    wrongDirection: false,
    groupMovement: false,
    nightMovement: true,
    confidenceThreshold: 75,
  });

  function toggle(name) {
    setConfig((current) => ({
      ...current,
      [name]: !current[name],
    }));
  }

  function handleSave() {
    console.log("Detection configuration:", {
      cameraId: camera.id,
      ...config,
    });

    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="panel flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden">
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between border-b border-line p-4">
          <div className="flex items-start gap-3">
            <div className="border border-line bg-panelSecondary p-2 text-info">
              <BrainCircuit size={17} />
            </div>

            <div>
              <p className="eyebrow">AI Detection</p>

              <h2 className="mt-1 text-sm font-semibold text-primary">
                Detection Configuration
              </h2>

              <p className="mt-1 text-[10px] text-muted">
                {camera.name} · {camera.id}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
            aria-label="Close detection configuration"
          >
            <X size={17} />
          </button>
        </div>

        {/* Detection Modules */}
        <div className="overflow-y-auto p-4">
          <p className="eyebrow">Detection Modules</p>

          <div className="mt-3 divide-y divide-line border border-line">
            <ToggleRow
              label="Person Detection"
              description="Detect and track people in the camera feed"
              enabled={config.personDetection}
              onToggle={() => toggle("personDetection")}
            />

            <ToggleRow
              label="Vehicle Detection"
              description="Detect and classify vehicles"
              enabled={config.vehicleDetection}
              onToggle={() => toggle("vehicleDetection")}
            />

            <ToggleRow
              label="Face Detection"
              description="Detect visible faces in the scene"
              enabled={config.faceDetection}
              onToggle={() => toggle("faceDetection")}
            />

            <ToggleRow
              label="ANPR"
              description="Automatic number plate recognition"
              enabled={config.anpr}
              onToggle={() => toggle("anpr")}
            />
          </div>

          {/* Behaviour Analysis */}
          <p className="eyebrow mt-6">Behaviour Analysis</p>

          <div className="mt-3 divide-y divide-line border border-line">
            <ToggleRow
              label="Loitering Detection"
              description="Identify prolonged presence in an area"
              enabled={config.loitering}
              onToggle={() => toggle("loitering")}
            />

            <ToggleRow
              label="Wrong Direction"
              description="Detect movement against configured direction"
              enabled={config.wrongDirection}
              onToggle={() => toggle("wrongDirection")}
            />

            <ToggleRow
              label="Group Movement"
              description="Identify multiple people moving together"
              enabled={config.groupMovement}
              onToggle={() => toggle("groupMovement")}
            />

            <ToggleRow
              label="Night Movement"
              description="Detect movement during low-light periods"
              enabled={config.nightMovement}
              onToggle={() => toggle("nightMovement")}
            />
          </div>

          {/* Confidence */}
          <div className="mt-6">
            <div className="flex items-center justify-between">
              <p className="eyebrow">Confidence Threshold</p>

              <span className="font-mono text-xs text-info">
                {config.confidenceThreshold}%
              </span>
            </div>

            <input
              type="range"
              min="50"
              max="100"
              value={config.confidenceThreshold}
              onChange={(e) =>
                setConfig((current) => ({
                  ...current,
                  confidenceThreshold: Number(e.target.value),
                }))
              }
              className="mt-4 w-full accent-info"
            />

            <div className="mt-1 flex justify-between text-[9px] text-muted">
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 justify-end gap-2 border-t border-line p-4">
          <button
            onClick={onClose}
            className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary"
          >
            Cancel
          </button>

          <button
            onClick={handleSave}
            className="border border-info bg-info/10 px-4 py-2 text-xs font-semibold text-info hover:bg-info/15"
          >
            Save Configuration
          </button>
        </div>
      </div>
    </div>
  );
}

function ToggleRow({ label, description, enabled, onToggle }) {
  return (
    <div className="flex items-center justify-between gap-4 bg-panel p-3">
      <div className="min-w-0">
        <p className="text-xs font-medium text-primary">{label}</p>

        <p className="mt-1 text-[10px] text-muted">{description}</p>
      </div>

      <button
  onClick={onToggle}
  type="button"
  className={`relative flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors ${
    enabled
      ? "border-info bg-info/20"
      : "border-line bg-panelSecondary"
  }`}
  aria-label={`Toggle ${label}`}
  aria-pressed={enabled}
>
  <span
    className={`block h-3.5 w-3.5 rounded-full transition-transform ${
      enabled
        ? "translate-x-[18px] bg-info"
        : "translate-x-[2px] bg-muted"
    }`}
  />
</button>
    </div>
  );
} 