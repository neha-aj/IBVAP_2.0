import { useEffect, useState } from "react";
import { Camera, X } from "lucide-react";

const emptyForm = {
  name: "",
  location: "",
  sector: "",
  type: "file",
  sourceUrl: "",
  file: null,
  thermalFile: null,
};

const TYPE_LABELS = {
  file: "Upload a video file",
  rtsp: "RTSP stream URL",
  ip: "IP camera URL",
  usb: "USB device index/URI",
  webcam: "Webcam device URI",
  thermal: "Thermal camera -- upload a video file",
  dual: "RGB + thermal pair -- upload two video files",
};

// M11: these two behave like 'file' (upload, not a URL) -- no real thermal
// hardware exists for this deployment, so testing needs an uploaded,
// looping video the same way every other camera type does.
const UPLOAD_BASED_TYPES = new Set(["file", "thermal", "dual"]);

export default function CameraForm({ camera, onSave, onClose }) {
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const isEditing = Boolean(camera);

  useEffect(() => {
    if (camera) {
      setForm({
        name: camera.name || "",
        location: camera.location || "",
        sector: camera.sector || "",
        type: camera.type || "file",
        sourceUrl: "",
        file: null,
      });
    } else {
      setForm(emptyForm);
    }
  }, [camera]);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  function handleFileChange(e) {
    setForm((current) => ({ ...current, file: e.target.files?.[0] || null }));
  }

  function handleThermalFileChange(e) {
    setForm((current) => ({ ...current, thermalFile: e.target.files?.[0] || null }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!form.name.trim() || !form.location.trim()) return;
    if (!isEditing && UPLOAD_BASED_TYPES.has(form.type) && !form.file) {
      setError("Choose a video file to upload.");
      return;
    }
    if (!isEditing && form.type === "dual" && !form.thermalFile) {
      setError("Choose a thermal video file to upload.");
      return;
    }
    if (!isEditing && !UPLOAD_BASED_TYPES.has(form.type) && !form.sourceUrl.trim()) {
      setError("Enter a source URL.");
      return;
    }

    setSubmitting(true);
    try {
      await onSave(form);
    } catch (err) {
      setError(err.detail || err.message || "Failed to save camera.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="panel w-full max-w-lg overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-line p-4">
          <div className="flex items-start gap-3">
            <div className="border border-line bg-panelSecondary p-2 text-info">
              <Camera size={17} />
            </div>

            <div>
              <p className="eyebrow">
                {isEditing ? "Edit Camera" : "Add Camera"}
              </p>

              <h2 className="mt-1 text-sm font-semibold text-primary">
                {isEditing
                  ? "Update camera configuration"
                  : "Register a new surveillance camera"}
              </h2>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
            aria-label="Close"
          >
            <X size={17} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 p-4">
            <Field
              label="Camera Name"
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="e.g. North Perimeter"
              required
            />

            <Field
              label="Location"
              name="location"
              value={form.location}
              onChange={handleChange}
              placeholder="e.g. BOP 01 — Sector A"
              required
            />

            <Field
              label="Sector (optional)"
              name="sector"
              value={form.sector}
              onChange={handleChange}
              placeholder="e.g. Alpha"
            />

            {isEditing ? (
              <p className="text-[11px] text-muted">
                Source type ({TYPE_LABELS[form.type] || form.type}) can't be changed after creation.
              </p>
            ) : (
              <>
                <SelectField
                  label="Source Type"
                  name="type"
                  value={form.type}
                  onChange={handleChange}
                  options={Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label }))}
                />

                {UPLOAD_BASED_TYPES.has(form.type) ? (
                  <>
                    <label className="block">
                      <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                        {form.type === "dual" ? "RGB Video File" : "Video File"}
                      </span>
                      <input
                        type="file"
                        accept="video/*"
                        onChange={handleFileChange}
                        className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-secondary outline-none file:mr-3 file:border-0 file:bg-info/10 file:px-3 file:py-1.5 file:text-info"
                      />
                    </label>

                    {form.type === "dual" && (
                      <label className="block">
                        <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                          Thermal Video File
                        </span>
                        <input
                          type="file"
                          accept="video/*"
                          onChange={handleThermalFileChange}
                          className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-secondary outline-none file:mr-3 file:border-0 file:bg-info/10 file:px-3 file:py-1.5 file:text-info"
                        />
                      </label>
                    )}
                  </>
                ) : (
                  <Field
                    label="Source URL"
                    name="sourceUrl"
                    value={form.sourceUrl}
                    onChange={handleChange}
                    placeholder="e.g. rtsp://192.168.1.10/stream"
                  />
                )}
              </>
            )}
          </div>

          {error && <p className="px-4 text-xs text-danger">{error}</p>}

          {/* Footer */}
          <div className="flex justify-end gap-2 border-t border-line p-4">
            <button
              type="button"
              onClick={onClose}
              className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={submitting}
              className="border border-info bg-info/10 px-4 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Saving..." : isEditing ? "Save Changes" : "Add Camera"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  name,
  value,
  onChange,
  placeholder,
  type = "text",
  required = false,
  min,
  max,
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
        {label}
      </span>

      <input
        type={type}
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        min={min}
        max={max}
        className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
      />
    </label>
  );
}

function SelectField({
  label,
  name,
  value,
  onChange,
  options,
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
        {label}
      </span>

      <select
        name={name}
        value={value}
        onChange={onChange}
        className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-secondary outline-none focus:border-info"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
