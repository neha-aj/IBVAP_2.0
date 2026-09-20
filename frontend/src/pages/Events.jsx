import { useState } from "react";
import { Download } from "lucide-react";
import PageHeader from "../components/layout/PageHeader";
import EventFilters from "../components/events/EventFilters";
import EventTable from "../components/events/EventTable";
import EmptyState from "../components/common/EmptyState";
import { useEvents } from "../hooks/useEvents";
import { useEventFilterOptions } from "../hooks/useEventFilterOptions";
import { EXPORT_MAX_ROWS, eventService } from "../services/eventService";
import { exportToCsv } from "../utils/exportToCsv";
import { EMPTY_FILTERS, filtersFileLabel, hasActiveFilters, toQueryParams } from "../utils/eventFilters";

const EXPORT_COLUMNS = [
  { label: "Time", value: (e) => new Date(e.time).toLocaleString() },
  { label: "Camera", value: (e) => e.cameraName },
  { label: "Event", value: (e) => e.event },
  { label: "Description", value: (e) => e.description || "" },
  { label: "Object", value: (e) => e.objectType || "" },
  { label: "Location", value: (e) => e.location || "" },
  { label: "Severity", value: (e) => e.severity },
  { label: "Status", value: (e) => e.status },
];

export default function Events() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const { events, total, hasMore, loadMore, isLoading, isLoadingMore, error } = useEvents(filters);
  const options = useEventFilterOptions();

  const [exporting, setExporting] = useState(null); // null | { done, total }
  const [exportNote, setExportNote] = useState(null);

  const filtered = hasActiveFilters(filters);

  async function handleExport() {
    setExportNote(null);
    setExporting({ done: 0, total });
    try {
      // Everything that matches the filters -- not just the rows currently on
      // screen -- so exporting one camera gives that camera's whole history.
      const result = await eventService.getAllMatching(toQueryParams(filters), {
        onProgress: (done, of) => setExporting({ done, total: of }),
      });
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      const cameraName = options.cameras.find((c) => c.id === filters.camera)?.name;
      const label = filtersFileLabel(filters, cameraName);
      exportToCsv(`events${label ? `-${label}` : ""}-${stamp}.csv`, result.items, EXPORT_COLUMNS);
      setExportNote(
        result.truncated
          ? `Exported the most recent ${result.items.length.toLocaleString()} of ${result.total.toLocaleString()} matching events (the export limit). Narrow the filters to export the rest.`
          : `Exported ${result.items.length.toLocaleString()} event${result.items.length === 1 ? "" : "s"}.`
      );
    } catch (err) {
      setExportNote(`Export failed: ${err.detail || err.message || "please try again."}`);
    } finally {
      setExporting(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Event History"
        subtitle="Recorded surveillance events and operational status"
        action={
          <button
            onClick={handleExport}
            disabled={total === 0 || exporting !== null}
            className="flex items-center gap-2 border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:bg-slate-800/40 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Download size={14} />
            {exporting
              ? `Exporting ${exporting.done.toLocaleString()} / ${exporting.total.toLocaleString()}...`
              : `Export to Excel${total > 0 ? ` (${Math.min(total, EXPORT_MAX_ROWS).toLocaleString()})` : ""}`}
          </button>
        }
      />
      <EventFilters
        filters={filters}
        onChange={setFilters}
        onClear={() => setFilters(EMPTY_FILTERS)}
        options={options}
      />
      {exportNote && (
        <div role="status" className="mb-3 flex items-center justify-between border border-info/40 bg-info/10 px-3 py-2 text-xs text-info">
          <span>{exportNote}</span>
          <button type="button" onClick={() => setExportNote(null)} className="ml-3 font-semibold hover:text-primary">
            Dismiss
          </button>
        </div>
      )}
      {isLoading ? (
        <div className="panel p-10 text-center text-xs text-muted">Loading events...</div>
      ) : error && events.length === 0 ? (
        <div className="panel p-10 text-center text-xs text-danger">Failed to load events.</div>
      ) : events.length === 0 ? (
        <EmptyState title="No events match these filters" />
      ) : (
        <>
          <p className="mb-2 text-[11px] text-muted">
            Showing {events.length.toLocaleString()} of {total.toLocaleString()} {filtered ? "matching " : ""}events
          </p>
          <EventTable events={events} />
          {hasMore && (
            <div className="mt-3 flex justify-center">
              <button
                type="button"
                onClick={loadMore}
                disabled={isLoadingMore}
                className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary disabled:opacity-50"
              >
                {isLoadingMore ? "Loading..." : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
