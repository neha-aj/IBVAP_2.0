import { useEffect, useState } from "react";
import { MapPin, X, RotateCcw, Save, Plus, Trash2, Spline } from "lucide-react";
import { zoneService } from "../../services/zoneService";
import { cameraService } from "../../services/cameraService";
import { GATEWAY_ORIGIN } from "../../services/api";

const DEFAULT_POLYGON = [
  { x: 20, y: 25 },
  { x: 80, y: 25 },
  { x: 80, y: 75 },
  { x: 20, y: 75 },
];
const DEFAULT_LINE = [{ x: 20, y: 50 }, { x: 80, y: 50 }];

// "queue" added Phase 2 M14 (Queue Detection) -- see camera-service's
// ZoneType literal.
const ZONE_TYPES = ["restricted", "perimeter", "general", "queue"];

// Line direction values match event-alert-service's own
// `line_crossing.crossing_direction()` convention exactly ("a_to_b" /
// "b_to_a") -- a line with no direction configured only ever produces
// plain "Line Crossing" alerts; one with a direction set produces
// "Wrong-Way Movement" whenever the actual crossing goes the other way
// (Phase 2 M13/M14).
const LINE_DIRECTIONS = [
  { value: "", label: "None (either direction)" },
  { value: "a_to_b", label: "Point A -> Point B only" },
  { value: "b_to_a", label: "Point B -> Point A only" },
];

// Behavioral analytics: marks a line as a perimeter barrier rather than an
// ordinary road/lane boundary -- event-alert-service's `_check_line_
// crossing` reports "Fence Climbing Detected" instead of the generic Line
// Crossing/Wrong-Way labels for a person crossing a "fence" line. Empty
// string (every line created before this feature, and every plain
// boundary line) behaves exactly as before.
const LINE_TYPES = [
  { value: "", label: "Boundary (plain line/wrong-way)" },
  { value: "fence", label: "Fence (perimeter barrier)" },
];

export default function VirtualFenceConfig({ camera, onClose }) {
  const [streamUrl, setStreamUrl] = useState(null);
  const [zones, setZones] = useState([]);
  const [lines, setLines] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [mode, setMode] = useState("zone"); // "zone" | "line"
  const [selected, setSelected] = useState(null); // { type: 'zone'|'line', id } | null (null = drafting new)

  const [name, setName] = useState("Restricted Zone");
  const [zoneType, setZoneType] = useState("restricted");
  const [points, setPoints] = useState(DEFAULT_POLYGON);
  const [linePoints, setLinePoints] = useState(DEFAULT_LINE);
  // Phase 2 M14 config surfaces: density_threshold (Crowd Density, zones
  // only) and direction (Wrong-Way, lines only). Both optional -- empty
  // string means "not configured", matching the backend's null default.
  const [densityThreshold, setDensityThreshold] = useState("");
  const [direction, setDirection] = useState("");
  const [lineType, setLineType] = useState("");
  // Phase 2 M21 PPE Detection: opt-in per zone, zones only.
  const [requiresPpe, setRequiresPpe] = useState(false);

  async function loadAll() {
    setIsLoading(true);
    setError("");
    try {
      const [zoneList, lineList] = await Promise.all([
        zoneService.getZones(camera.id),
        zoneService.getZoneLines(camera.id),
      ]);
      setZones(zoneList);
      setLines(lineList);
    } catch (err) {
      setError(err.detail || err.message || "Failed to load zones.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    cameraService.getStream(camera.id).then((info) => {
      setStreamUrl(`${GATEWAY_ORIGIN}${info.mjpegUrl}`);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  function startNewZone() {
    setSelected(null);
    setMode("zone");
    setName("Restricted Zone");
    setZoneType("restricted");
    setPoints(DEFAULT_POLYGON);
    setDensityThreshold("");
    setRequiresPpe(false);
  }

  function startNewLine() {
    setSelected(null);
    setMode("line");
    setName("Boundary Line");
    setLinePoints(DEFAULT_LINE);
    setDirection("");
    setLineType("");
  }

  function selectZone(zone) {
    setSelected({ type: "zone", id: zone.id });
    setMode("zone");
    setName(zone.name);
    setZoneType(zone.zoneType);
    setPoints(zone.polygon);
    setDensityThreshold(zone.densityThreshold ?? "");
    setRequiresPpe(zone.requiresPpe ?? false);
  }

  function selectLine(line) {
    setSelected({ type: "line", id: line.id });
    setMode("line");
    setName(line.name);
    setLinePoints([line.pointA, line.pointB]);
    setDirection(line.direction ?? "");
    setLineType(line.lineType ?? "");
  }

  function handleCanvasClick(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));

    if (mode === "zone") {
      setPoints((current) => [...current, { x, y }]);
    } else {
      // A line is exactly two points -- the third click starts a fresh line.
      setLinePoints((current) => (current.length >= 2 ? [{ x, y }] : [...current, { x, y }]));
    }
  }

  function resetDraft() {
    if (mode === "zone") setPoints(DEFAULT_POLYGON);
    else setLinePoints(DEFAULT_LINE);
  }

  function removeZonePoint(index) {
    setPoints((current) => current.filter((_, i) => i !== index));
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      if (mode === "zone") {
        const payload = {
          name,
          polygon: points,
          zoneType,
          densityThreshold: densityThreshold === "" ? null : Number(densityThreshold),
          requiresPpe,
        };
        if (selected?.type === "zone") {
          await zoneService.updateZone(camera.id, selected.id, payload);
        } else {
          await zoneService.createZone(camera.id, payload);
        }
      } else {
        const payload = {
          name,
          pointA: linePoints[0],
          pointB: linePoints[1],
          direction: direction === "" ? null : direction,
          lineType: lineType === "" ? null : lineType,
        };
        if (selected?.type === "line") {
          await zoneService.updateZoneLine(camera.id, selected.id, payload);
        } else {
          await zoneService.createZoneLine(camera.id, payload);
        }
      }
      await loadAll();
    } catch (err) {
      setError(err.detail || err.message || "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(type, id) {
    try {
      if (type === "zone") await zoneService.deleteZone(camera.id, id);
      else await zoneService.deleteZoneLine(camera.id, id);
      if (selected?.type === type && selected.id === id) {
        type === "zone" ? startNewZone() : startNewLine();
      }
      await loadAll();
    } catch (err) {
      setError(err.detail || err.message || "Failed to delete.");
    }
  }

  const polygonPoints = points.map((p) => `${p.x},${p.y}`).join(" ");
  const canSave = mode === "zone" ? points.length >= 3 : linePoints.length === 2;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="panel flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden">
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between border-b border-line p-4">
          <div className="flex items-start gap-3">
            <div className="border border-line bg-panelSecondary p-2 text-info">
              <MapPin size={17} />
            </div>
            <div>
              <p className="eyebrow">Zone &amp; Line Editor</p>
              <h2 className="mt-1 text-sm font-semibold text-primary">Configure Zones &amp; Lines</h2>
              <p className="mt-1 text-[10px] text-muted">{camera.name} · {camera.id}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-muted hover:bg-panelSecondary hover:text-primary" aria-label="Close zone editor">
            <X size={17} />
          </button>
        </div>

        <div className="grid gap-5 overflow-y-auto p-4 lg:grid-cols-[1fr_260px]">
          {/* Editor */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="eyebrow">{mode === "zone" ? "Zone Editor" : "Line Editor"}</p>
                <p className="mt-1 text-[10px] text-muted">
                  {mode === "zone"
                    ? "Click inside the frame to add polygon points"
                    : "Click twice inside the frame to place a line's two endpoints"}
                </p>
              </div>
              <button
                type="button"
                onClick={resetDraft}
                className="flex items-center gap-1 border border-line bg-panelSecondary px-2 py-1.5 text-[10px] text-secondary hover:text-primary"
              >
                <RotateCcw size={12} />
                Reset
              </button>
            </div>

            <div
              onClick={handleCanvasClick}
              className="relative aspect-video cursor-crosshair overflow-hidden border border-line bg-black"
            >
              {streamUrl && (
                <img src={streamUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
              )}

              <div className="absolute left-3 top-3">
                <p className="font-mono text-[10px] text-primary">{camera.id}</p>
                <p className="mt-1 text-[9px] text-muted">
                  {mode === "zone" ? "ZONE EDIT MODE" : "LINE EDIT MODE"}
                </p>
              </div>

              <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
                {/* Existing zones/lines shown faint for context */}
                {zones.filter((z) => !(selected?.type === "zone" && selected.id === z.id)).map((z) => (
                  <polygon
                    key={z.id}
                    points={z.polygon.map((p) => `${p.x},${p.y}`).join(" ")}
                    fill="rgba(148,163,184,0.08)"
                    stroke="rgba(148,163,184,0.4)"
                    strokeWidth="0.5"
                  />
                ))}
                {lines.filter((l) => !(selected?.type === "line" && selected.id === l.id)).map((l) => (
                  <line
                    key={l.id}
                    x1={l.pointA.x} y1={l.pointA.y} x2={l.pointB.x} y2={l.pointB.y}
                    stroke="rgba(148,163,184,0.4)" strokeWidth="0.6" strokeDasharray="2,2"
                  />
                ))}

                {mode === "zone" && points.length >= 3 && (
                  <polygon points={polygonPoints} fill="rgba(59,130,246,0.12)" stroke="rgb(59,130,246)" strokeWidth="0.7" />
                )}
                {mode === "zone" && points.map((point, index) => (
                  <circle
                    key={index} cx={point.x} cy={point.y} r="1.8"
                    fill="rgb(59,130,246)" stroke="white" strokeWidth="0.5"
                    onClick={(e) => { e.stopPropagation(); removeZonePoint(index); }}
                  />
                ))}

                {mode === "line" && linePoints.length === 2 && (
                  <line
                    x1={linePoints[0].x} y1={linePoints[0].y} x2={linePoints[1].x} y2={linePoints[1].y}
                    stroke="rgb(245,158,11)" strokeWidth="0.9"
                  />
                )}
                {mode === "line" && linePoints.map((point, index) => (
                  <circle key={index} cx={point.x} cy={point.y} r="1.8" fill="rgb(245,158,11)" stroke="white" strokeWidth="0.5" />
                ))}
              </svg>

              {mode === "zone" && points.length >= 3 && (
                <div
                  className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 border border-info bg-panel/90 px-2 py-1"
                  style={{
                    left: `${points.reduce((sum, p) => sum + p.x, 0) / points.length}%`,
                    top: `${points.reduce((sum, p) => sum + p.y, 0) / points.length}%`,
                  }}
                >
                  <p className="text-[9px] font-bold uppercase tracking-wider text-info">{name}</p>
                </div>
              )}

              <div className="absolute bottom-3 left-3 border border-line bg-panel/90 px-2 py-1">
                <p className="font-mono text-[9px] text-secondary">
                  {mode === "zone" ? `${points.length} POINTS` : `${linePoints.length}/2 POINTS`}
                </p>
              </div>
            </div>

            {mode === "zone" && (
              <p className="mt-2 text-[10px] text-muted">Click a point to remove it.</p>
            )}
          </div>

          {/* Settings + list */}
          <div className="space-y-4">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={startNewZone}
                className={`flex flex-1 items-center justify-center gap-1 border px-2 py-1.5 text-[10px] font-semibold ${mode === "zone" && !selected ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary hover:text-primary"}`}
              >
                <Plus size={12} /> New Zone
              </button>
              <button
                type="button"
                onClick={startNewLine}
                className={`flex flex-1 items-center justify-center gap-1 border px-2 py-1.5 text-[10px] font-semibold ${mode === "line" && !selected ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary hover:text-primary"}`}
              >
                <Spline size={12} /> New Line
              </button>
            </div>

            <label className="block">
              <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none focus:border-info"
              />
            </label>

            {mode === "zone" && (
              <>
                <label className="block">
                  <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">Zone Type</span>
                  <select
                    value={zoneType}
                    onChange={(e) => setZoneType(e.target.value)}
                    className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-secondary outline-none focus:border-info"
                  >
                    {ZONE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>

                <label className="block">
                  <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                    Density Threshold <span className="normal-case text-muted/70">(optional)</span>
                  </span>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    value={densityThreshold}
                    onChange={(e) => setDensityThreshold(e.target.value)}
                    placeholder="e.g. 0.02"
                    className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
                  />
                  <span className="mt-1 block text-[9px] leading-4 text-muted">
                    People per unit zone area. Leave empty to disable Crowd Density alerts for this zone.
                  </span>
                </label>

                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={requiresPpe}
                    onChange={(e) => setRequiresPpe(e.target.checked)}
                    className="h-3.5 w-3.5 border-line accent-info"
                  />
                  <span className="text-[10px] font-semibold text-secondary">Requires PPE (hard hat, hi-vis vest)</span>
                </label>
              </>
            )}

            {mode === "line" && (
              <label className="block">
                <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                  Direction <span className="normal-case text-muted/70">(optional)</span>
                </span>
                <select
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                  className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-secondary outline-none focus:border-info"
                >
                  {LINE_DIRECTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
                <span className="mt-1 block text-[9px] leading-4 text-muted">
                  Crossing against this direction raises a Wrong-Way Movement alert instead of a plain Line Crossing.
                </span>
              </label>
            )}

            {mode === "line" && (
              <label className="block">
                <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">
                  Line Type <span className="normal-case text-muted/70">(optional)</span>
                </span>
                <select
                  value={lineType}
                  onChange={(e) => setLineType(e.target.value)}
                  className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-secondary outline-none focus:border-info"
                >
                  {LINE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
                <span className="mt-1 block text-[9px] leading-4 text-muted">
                  A person crossing a Fence line raises a Fence Climbing Detected alert instead.
                </span>
              </label>
            )}

            {error && <p className="text-xs text-danger">{error}</p>}

            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave || saving}
              className="flex w-full items-center justify-center gap-2 border border-info bg-info/10 px-4 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Save size={14} />
              {saving ? "Saving..." : selected ? "Save Changes" : mode === "zone" ? "Add Zone" : "Add Line"}
            </button>

            <div className="border-t border-line pt-3">
              <p className="eyebrow">Configured ({zones.length + lines.length})</p>
              {isLoading ? (
                <p className="mt-2 text-[10px] text-muted">Loading...</p>
              ) : (
                <div className="mt-2 max-h-52 space-y-1.5 overflow-y-auto">
                  {zones.length === 0 && lines.length === 0 && (
                    <p className="text-[10px] text-muted">No zones configured for this camera.</p>
                  )}
                  {zones.map((z) => (
                    <ListItem
                      key={z.id}
                      label={z.name}
                      tag="ZONE"
                      active={selected?.type === "zone" && selected.id === z.id}
                      onSelect={() => selectZone(z)}
                      onDelete={() => handleDelete("zone", z.id)}
                    />
                  ))}
                  {lines.map((l) => (
                    <ListItem
                      key={l.id}
                      label={l.name}
                      tag="LINE"
                      active={selected?.type === "line" && selected.id === l.id}
                      onSelect={() => selectLine(l)}
                      onDelete={() => handleDelete("line", l.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 justify-end gap-2 border-t border-line p-4">
          <button
            type="button"
            onClick={onClose}
            className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function ListItem({ label, tag, active, onSelect, onDelete }) {
  return (
    <div
      className={`flex items-center justify-between gap-2 border px-2 py-1.5 text-xs ${active ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary"}`}
    >
      <button type="button" onClick={onSelect} className="min-w-0 flex-1 truncate text-left hover:text-primary">
        <span className="mr-1.5 rounded-sm bg-panel px-1 py-0.5 text-[8px] font-bold tracking-wider text-muted">{tag}</span>
        {label}
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        aria-label={`Delete ${label}`}
        className="text-muted hover:text-danger"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}
