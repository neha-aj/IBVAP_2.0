import { useEffect, useState } from "react";
import { Gauge, X, Save } from "lucide-react";
import { cameraService } from "../../services/cameraService";

// Phase 2 M14 Speed Estimation (doc09 §1.2): a one-time admin-configured
// pixel-to-real-world mapping. Camera list responses (CameraRead) don't
// carry `calibration` -- only CameraDetail (GET /cameras/{id}) does -- so
// this fetches the detail record itself on open rather than trusting
// whatever summary object the caller passed in.
export default function CalibrationConfig({ camera, onClose }) {
  const [pixelDistance, setPixelDistance] = useState("");
  const [realWorldMeters, setRealWorldMeters] = useState("");
  const [thresholdKmh, setThresholdKmh] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    cameraService
      .getById(camera.id)
      .then((detail) => {
        if (cancelled) return;
        const calibration = detail.calibration;
        if (calibration) {
          setPixelDistance(String(calibration.pixelDistance));
          setRealWorldMeters(String(calibration.realWorldMeters));
          setThresholdKmh(String(calibration.thresholdKmh));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.detail || err.message || "Failed to load calibration.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [camera.id]);

  const canSave = pixelDistance !== "" && realWorldMeters !== "" && thresholdKmh !== "";

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await cameraService.update(camera.id, {
        calibration: {
          pixelDistance: Number(pixelDistance),
          realWorldMeters: Number(realWorldMeters),
          thresholdKmh: Number(thresholdKmh),
        },
      });
      onClose();
    } catch (err) {
      setError(err.detail || err.message || "Failed to save calibration.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="panel flex max-h-[90vh] w-full max-w-md flex-col overflow-hidden">
        <div className="flex shrink-0 items-start justify-between border-b border-line p-4">
          <div className="flex items-start gap-3">
            <div className="border border-line bg-panelSecondary p-2 text-info">
              <Gauge size={17} />
            </div>
            <div>
              <p className="eyebrow">Speed Estimation</p>
              <h2 className="mt-1 text-sm font-semibold text-primary">Speed Calibration</h2>
              <p className="mt-1 text-[10px] text-muted">{camera.name} &middot; {camera.id}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-muted hover:bg-panelSecondary hover:text-primary" aria-label="Close calibration config">
            <X size={17} />
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto p-4">
          <p className="text-[10px] leading-4 text-muted">
            Mark two points on this camera's frame a known real-world distance apart. Speed Estimation
            alerts (Phase 2 M14) stay disabled for this camera until all three values are set.
          </p>

          {isLoading ? (
            <p className="text-xs text-muted">Loading current calibration...</p>
          ) : (
            <>
              <label className="block">
                <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                  Pixel Distance <span className="normal-case text-muted/70">(% of frame width)</span>
                </span>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={pixelDistance}
                  onChange={(e) => setPixelDistance(e.target.value)}
                  placeholder="e.g. 25"
                  className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                  Real-World Distance <span className="normal-case text-muted/70">(meters)</span>
                </span>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={realWorldMeters}
                  onChange={(e) => setRealWorldMeters(e.target.value)}
                  placeholder="e.g. 10"
                  className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                  Speed Threshold <span className="normal-case text-muted/70">(km/h)</span>
                </span>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={thresholdKmh}
                  onChange={(e) => setThresholdKmh(e.target.value)}
                  placeholder="e.g. 30"
                  className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
                />
              </label>
            </>
          )}

          {error && <p className="text-xs text-danger">{error}</p>}
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-line p-4">
          <button
            type="button"
            onClick={onClose}
            className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave || saving || isLoading}
            className="flex items-center gap-2 border border-info bg-info/10 px-4 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Save size={14} />
            {saving ? "Saving..." : "Save Calibration"}
          </button>
        </div>
      </div>
    </div>
  );
}
