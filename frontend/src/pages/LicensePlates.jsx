import { useCallback, useEffect, useState } from "react";
import { CarFront, Plus, ShieldAlert, Trash2 } from "lucide-react";

import PageHeader from "../components/layout/PageHeader";
import EmptyState from "../components/common/EmptyState";
import Badge from "../components/common/Badge";
import { useAuth } from "../hooks/useAuth";
import { anprService } from "../services/anprService";
import { GATEWAY_ORIGIN } from "../services/api";

export default function LicensePlates() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [camera, setCamera] = useState("");
  const [plate, setPlate] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [reads, setReads] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [watchlist, setWatchlist] = useState([]);
  const [watchlistError, setWatchlistError] = useState("");
  const [newPlate, setNewPlate] = useState("");
  const [newReason, setNewReason] = useState("");
  const [adding, setAdding] = useState(false);

  const loadReads = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const data = await anprService.getReads({
        camera: camera || undefined,
        plate: plate || undefined,
        from: dateFrom || undefined,
        to: dateTo || undefined,
        page,
        pageSize,
      });
      setReads(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.detail || err.message || "Failed to load plate reads.");
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera, plate, dateFrom, dateTo, page]);

  const loadWatchlist = useCallback(async () => {
    setWatchlistError("");
    try {
      setWatchlist(await anprService.getWatchlist());
    } catch (err) {
      setWatchlistError(err.detail || err.message || "Failed to load watchlist.");
    }
  }, []);

  useEffect(() => {
    loadReads();
  }, [loadReads]);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  async function handleAddWatchlist(e) {
    e.preventDefault();
    if (!newPlate.trim()) return;
    setAdding(true);
    setWatchlistError("");
    try {
      await anprService.addWatchlistEntry({ plateText: newPlate.trim(), reason: newReason.trim() || undefined });
      setNewPlate("");
      setNewReason("");
      await loadWatchlist();
    } catch (err) {
      setWatchlistError(err.detail || err.message || "Failed to add watchlist entry.");
    } finally {
      setAdding(false);
    }
  }

  async function handleDeleteWatchlist(id) {
    setWatchlistError("");
    try {
      await anprService.deleteWatchlistEntry(id);
      await loadWatchlist();
    } catch (err) {
      setWatchlistError(err.detail || err.message || "Failed to remove watchlist entry.");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <PageHeader
        title="License Plate Recognition"
        subtitle="Automatic Number Plate Recognition reads and watchlist matches"
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          {/* Filters */}
          <section className="panel mb-5 flex flex-wrap items-center gap-3 p-3">
            <input
              value={plate}
              onChange={(e) => { setPage(1); setPlate(e.target.value); }}
              placeholder="Search plate text..."
              className="min-w-40 flex-1 border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
            />
            <input
              value={camera}
              onChange={(e) => { setPage(1); setCamera(e.target.value); }}
              placeholder="Camera ID..."
              className="w-40 border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
            />
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => { setPage(1); setDateFrom(e.target.value); }}
              className="border border-line bg-panelSecondary px-3 py-2 text-xs text-secondary outline-none focus:border-info"
            />
            <input
              type="date"
              value={dateTo}
              onChange={(e) => { setPage(1); setDateTo(e.target.value); }}
              className="border border-line bg-panelSecondary px-3 py-2 text-xs text-secondary outline-none focus:border-info"
            />
          </section>

          {isLoading ? (
            <div className="panel p-10 text-center text-xs text-muted">Loading plate reads...</div>
          ) : error ? (
            <div className="panel p-10 text-center text-xs text-danger">{error}</div>
          ) : reads.length === 0 ? (
            <EmptyState title="No plate reads match these filters" />
          ) : (
            <>
              <div className="panel overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-line text-[10px] uppercase tracking-wider text-muted">
                      <th className="p-3 font-semibold">Snapshot</th>
                      <th className="p-3 font-semibold">Plate</th>
                      <th className="p-3 font-semibold">Camera</th>
                      <th className="p-3 font-semibold">Confidence</th>
                      <th className="p-3 font-semibold">Time</th>
                      <th className="p-3 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reads.map((read) => (
                      <tr key={read.id} className="border-b border-line last:border-0 hover:bg-panelSecondary">
                        <td className="p-3">
                          {read.snapshotUrl ? (
                            <img
                              src={`${GATEWAY_ORIGIN}${read.snapshotUrl}`}
                              alt=""
                              className="h-10 w-16 rounded-sm border border-line object-cover"
                            />
                          ) : (
                            <div className="flex h-10 w-16 items-center justify-center border border-line bg-panelSecondary text-muted">
                              <CarFront size={14} />
                            </div>
                          )}
                        </td>
                        <td className="p-3 font-mono font-semibold text-primary">{read.plateText}</td>
                        <td className="p-3 text-secondary">{read.cameraId}</td>
                        <td className="p-3 text-secondary">{(read.confidence * 100).toFixed(0)}%</td>
                        <td className="p-3 text-muted">{new Date(read.createdAt).toLocaleString()}</td>
                        <td className="p-3">
                          {read.watchlistMatch ? (
                            <Badge tone="offline">
                              <ShieldAlert size={10} className="mr-1 inline" />
                              Watchlist
                            </Badge>
                          ) : (
                            <Badge tone="neutral">Clear</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
                <span>
                  Page {page} of {totalPages} &middot; {total} total reads
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="border border-line bg-panelSecondary px-2 py-1 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Prev
                  </button>
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="border border-line bg-panelSecondary px-2 py-1 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Watchlist panel */}
        <section className="panel h-fit overflow-hidden">
          <div className="border-b border-line p-4">
            <p className="eyebrow">Plate Watchlist</p>
            <p className="mt-1 text-[10px] text-muted">Reads matching these plates are flagged automatically.</p>
          </div>

          {isAdmin && (
            <form onSubmit={handleAddWatchlist} className="space-y-2 border-b border-line p-4">
              <input
                value={newPlate}
                onChange={(e) => setNewPlate(e.target.value.toUpperCase())}
                placeholder="Plate text"
                className="w-full border border-line bg-panelSecondary px-3 py-2 text-xs font-mono text-primary outline-none placeholder:font-sans placeholder:text-muted focus:border-info"
              />
              <input
                value={newReason}
                onChange={(e) => setNewReason(e.target.value)}
                placeholder="Reason (optional)"
                className="w-full border border-line bg-panelSecondary px-3 py-2 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
              />
              <button
                type="submit"
                disabled={!newPlate.trim() || adding}
                className="flex w-full items-center justify-center gap-2 border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus size={13} />
                {adding ? "Adding..." : "Add to Watchlist"}
              </button>
            </form>
          )}

          {watchlistError && <p className="p-4 text-xs text-danger">{watchlistError}</p>}

          <div className="max-h-96 space-y-1.5 overflow-y-auto p-4">
            {watchlist.length === 0 ? (
              <p className="text-[10px] text-muted">No watchlist entries.</p>
            ) : (
              watchlist.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between gap-2 border border-line bg-panelSecondary px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-xs font-semibold text-primary">{entry.plateText}</p>
                    {entry.reason && <p className="truncate text-[10px] text-muted">{entry.reason}</p>}
                  </div>
                  {isAdmin && (
                    <button
                      onClick={() => handleDeleteWatchlist(entry.id)}
                      aria-label={`Remove ${entry.plateText} from watchlist`}
                      className="shrink-0 text-muted hover:text-danger"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
