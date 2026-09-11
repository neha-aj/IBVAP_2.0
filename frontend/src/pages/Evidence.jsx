import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

import PageHeader from "../components/layout/PageHeader";
import EvidenceList from "../components/evidence/EvidenceList";
import { eventService } from "../services/eventService";

// Evidence page: every event with an attached recording clip -- the
// pre+post-roll capture that fires automatically for critical-severity
// events (see event-alert-service's recording_client.py). This page is
// the "view it easily / export it" half of that feature; capture itself
// is unchanged, entirely backend-side, and already working.
export default function Evidence() {
  const [evidence, setEvidence] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");

  const [selectedEvidence, setSelectedEvidence] = useState(null);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const items = await eventService.getAll({ hasRecording: true });
      setEvidence(items);
      setSelectedEvidence((current) =>
        current ? items.find((item) => item.id === current.id) || null : null
      );
    } catch (err) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredEvidence = useMemo(() => {
    const query = search.toLowerCase();
    return evidence.filter((item) => {
      const matchesSearch =
        !query ||
        item.cameraName.toLowerCase().includes(query) ||
        item.event.toLowerCase().includes(query) ||
        (item.location || "").toLowerCase().includes(query);

      const matchesSeverity = severity === "all" || item.severity === severity;

      return matchesSearch && matchesSeverity;
    });
  }, [evidence, search, severity]);

  return (
    <div>
      <PageHeader
        title="Evidence Recordings"
        subtitle="Pre + post-roll clips captured automatically for critical-severity events"
        action={
          <button
            onClick={load}
            className="flex items-center gap-2 border border-line bg-panelSecondary px-3 py-2 text-xs font-semibold text-secondary hover:bg-slate-800/40"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        }
      />

      <section className="panel mb-5 flex flex-wrap items-center gap-3 p-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by camera, event, or location..."
          className="min-w-52 flex-1 border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
        />

        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="border border-line bg-panelSecondary p-2 text-xs text-secondary outline-none focus:border-info"
        >
          <option value="all">All severity</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </section>

      {isLoading ? (
        <div className="panel p-10 text-center text-xs text-muted">Loading evidence...</div>
      ) : error ? (
        <div className="panel p-10 text-center text-xs text-danger">Failed to load evidence recordings.</div>
      ) : (
        <div>
          <div className="mb-3">
            <p className="eyebrow">Recorded Clips</p>
            <p className="mt-1 text-[11px] text-muted">
              Showing {filteredEvidence.length} of {evidence.length} recordings
            </p>
          </div>

          <EvidenceList
            evidence={filteredEvidence}
            selectedEvidence={selectedEvidence}
            onSelect={setSelectedEvidence}
          />
        </div>
      )}
    </div>
  );
}
