import { Download } from "lucide-react";
import PageHeader from "../components/layout/PageHeader";
import EventFilters from "../components/events/EventFilters";
import EventTable from "../components/events/EventTable";
import EmptyState from "../components/common/EmptyState";
import { useEvents } from "../hooks/useEvents";
import { exportToCsv } from "../utils/exportToCsv";

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
  const { events, isLoading, error } = useEvents();

  function handleExport() {
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    exportToCsv(`events-${stamp}.csv`, events, EXPORT_COLUMNS);
  }

  return (
    <>
      <PageHeader
        title="Event History"
        subtitle="Recorded surveillance events and operational status"
        action={
          <button
            onClick={handleExport}
            disabled={events.length === 0}
            className="flex items-center gap-2 border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:bg-slate-800/40 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Download size={14} />
            Export to Excel
          </button>
        }
      />
      <EventFilters />
      {isLoading ? (
        <div className="panel p-10 text-center text-xs text-muted">Loading events...</div>
      ) : error ? (
        <div className="panel p-10 text-center text-xs text-danger">Failed to load events.</div>
      ) : events.length === 0 ? (
        <EmptyState title="No events match these filters" />
      ) : (
        <EventTable events={events} />
      )}
    </>
  );
}
