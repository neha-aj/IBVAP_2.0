import { DATE_PRESETS, SEVERITY_LABELS, hasActiveFilters } from "../../utils/eventFilters";

const SELECT_CLASS =
  "mt-1 block w-full rounded-sm border border-line bg-[#0b141c] p-2 text-slate-300 outline-none focus:border-info";

function count(n) {
  return n === undefined || n === null ? "" : ` (${n.toLocaleString()})`;
}

// Camera / event type / severity / date pickers for the Events page. Fully
// controlled: the page owns `filters` and refetches from the server whenever
// they change, so a selection filters *every* stored event, not just the ones
// already on screen.
export default function EventFilters({ filters, onChange, onClear, options }) {
  const set = (patch) => onChange({ ...filters, ...patch });

  return (
    <div className="panel mb-4 p-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-xs text-muted">
          Camera
          <select className={SELECT_CLASS} value={filters.camera} onChange={(e) => set({ camera: e.target.value })}>
            <option value="">All Cameras</option>
            {options.cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {count(c.count)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-muted">
          Event type
          <select className={SELECT_CLASS} value={filters.eventType} onChange={(e) => set({ eventType: e.target.value })}>
            <option value="">All Event Types</option>
            {options.eventTypes.map((t) => (
              <option key={t.value} value={t.value}>
                {t.value}
                {count(t.count)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-muted">
          Severity
          <select className={SELECT_CLASS} value={filters.severity} onChange={(e) => set({ severity: e.target.value })}>
            <option value="">All Severities</option>
            {options.severities.map((s) => (
              <option key={s.value} value={s.value}>
                {SEVERITY_LABELS[s.value] || s.value}
                {count(s.count)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-muted">
          Date
          <select className={SELECT_CLASS} value={filters.datePreset} onChange={(e) => set({ datePreset: e.target.value })}>
            {DATE_PRESETS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {filters.datePreset === "custom" && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs text-muted">
            From
            <input
              type="date"
              className={SELECT_CLASS}
              value={filters.customFrom}
              max={filters.customTo || undefined}
              onChange={(e) => set({ customFrom: e.target.value })}
            />
          </label>
          <label className="text-xs text-muted">
            To
            <input
              type="date"
              className={SELECT_CLASS}
              value={filters.customTo}
              min={filters.customFrom || undefined}
              onChange={(e) => set({ customTo: e.target.value })}
            />
          </label>
        </div>
      )}

      {hasActiveFilters(filters) && (
        <div className="mt-3">
          <button type="button" onClick={onClear} className="text-[11px] font-semibold text-info hover:underline">
            Clear all filters
          </button>
        </div>
      )}
    </div>
  );
}
