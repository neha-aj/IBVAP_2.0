import { useRef, useState } from "react";
import { CarFront, Search, Upload, UserRound } from "lucide-react";

import PageHeader from "../components/layout/PageHeader";
import EmptyState from "../components/common/EmptyState";
import { reidService } from "../services/reidService";
import { GATEWAY_ORIGIN } from "../services/api";

export default function PersonSearch() {
  // Phase 2 M17: same page/endpoints as M16's Person Re-ID, `objectType`
  // just picks which embedding index (person vs. vehicle) gets searched.
  const [objectType, setObjectType] = useState("person"); // "person" | "vehicle"
  const [mode, setMode] = useState("track"); // "track" | "upload"
  const [cameraId, setCameraId] = useState("");
  const [trackId, setTrackId] = useState("");
  const [uploadPreview, setUploadPreview] = useState(null);
  const fileInputRef = useRef(null);

  const [matches, setMatches] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");

  const TypeIcon = objectType === "vehicle" ? CarFront : UserRound;

  async function handleTrackSearch(e) {
    e.preventDefault();
    if (!cameraId.trim() || !trackId.trim()) return;
    setIsSearching(true);
    setError("");
    setMatches(null);
    try {
      setMatches(await reidService.searchByTrack(cameraId.trim(), trackId.trim(), objectType));
    } catch (err) {
      setError(err.detail || err.message || "Search failed.");
    } finally {
      setIsSearching(false);
    }
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadPreview(URL.createObjectURL(file));
    setIsSearching(true);
    setError("");
    setMatches(null);
    try {
      setMatches(await reidService.searchByImage(file, objectType));
    } catch (err) {
      setError(err.detail || err.message || "Search failed.");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Person & Vehicle Re-Identification"
        subtitle="Find every camera and time a person or vehicle of interest was seen"
      />

      <section className="panel mb-5 p-4">
        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => { setObjectType("person"); setMatches(null); }}
            className={`flex flex-1 items-center justify-center gap-1.5 border px-3 py-2 text-xs font-semibold ${objectType === "person" ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary hover:text-primary"}`}
          >
            <UserRound size={13} /> Person
          </button>
          <button
            type="button"
            onClick={() => { setObjectType("vehicle"); setMatches(null); }}
            className={`flex flex-1 items-center justify-center gap-1.5 border px-3 py-2 text-xs font-semibold ${objectType === "vehicle" ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary hover:text-primary"}`}
          >
            <CarFront size={13} /> Vehicle
          </button>
        </div>

        <div className="mb-4 flex gap-2">
          <button
            type="button"
            onClick={() => setMode("track")}
            className={`flex-1 border px-3 py-2 text-xs font-semibold ${mode === "track" ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary hover:text-primary"}`}
          >
            Search by Track
          </button>
          <button
            type="button"
            onClick={() => setMode("upload")}
            className={`flex-1 border px-3 py-2 text-xs font-semibold ${mode === "upload" ? "border-info bg-info/10 text-info" : "border-line bg-panelSecondary text-secondary hover:text-primary"}`}
          >
            Search by Photo
          </button>
        </div>

        {mode === "track" ? (
          <form onSubmit={handleTrackSearch} className="flex flex-wrap items-end gap-3">
            <label className="min-w-40 flex-1">
              <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">Camera ID</span>
              <input
                value={cameraId}
                onChange={(e) => setCameraId(e.target.value)}
                placeholder="e.g. FILE-C5F172A4"
                className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
              />
            </label>
            <label className="min-w-40 flex-1">
              <span className="mb-2 block text-[9px] font-bold uppercase tracking-wider text-muted">Track ID</span>
              <input
                value={trackId}
                onChange={(e) => setTrackId(e.target.value)}
                placeholder="e.g. 18893"
                className="w-full border border-line bg-panelSecondary px-3 py-2.5 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
              />
            </label>
            <button
              type="submit"
              disabled={!cameraId.trim() || !trackId.trim() || isSearching}
              className="flex items-center gap-2 border border-info bg-info/10 px-4 py-2.5 text-xs font-semibold text-info hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Search size={14} />
              {isSearching ? "Searching..." : "Search"}
            </button>
          </form>
        ) : (
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 border border-line bg-panelSecondary px-4 py-2.5 text-xs font-semibold text-secondary hover:text-primary"
            >
              <Upload size={14} />
              Choose Reference Photo
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
            />
            {uploadPreview && (
              <img src={uploadPreview} alt="Reference" className="h-14 w-14 rounded-sm border border-line object-cover" />
            )}
            {isSearching && <p className="text-xs text-muted">Searching...</p>}
          </div>
        )}

        {error && <p className="mt-3 text-xs text-danger">{error}</p>}
      </section>

      {matches === null ? (
        <div className="panel flex min-h-[220px] items-center justify-center p-6 text-center">
          <div>
            <TypeIcon size={20} className="mx-auto text-muted" />
            <p className="mt-3 text-sm font-semibold text-primary">No search run yet</p>
            <p className="mt-1 text-xs text-muted">
              Search by an existing track or upload a reference photo to find matching appearances.
            </p>
          </div>
        </div>
      ) : matches.length === 0 ? (
        <EmptyState title="No matching appearances found" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {matches.map((match, index) => (
            <article key={`${match.cameraId}-${match.trackId}-${index}`} className="panel overflow-hidden">
              {match.snapshotUrl ? (
                <img
                  src={`${GATEWAY_ORIGIN}${match.snapshotUrl}`}
                  alt=""
                  className="h-32 w-full object-cover"
                />
              ) : (
                <div className="flex h-32 w-full items-center justify-center bg-panelSecondary text-muted">
                  <TypeIcon size={20} />
                </div>
              )}
              <div className="p-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-primary">{match.cameraName}</p>
                  <p className="text-[10px] font-bold text-info">{(match.similarityScore * 100).toFixed(1)}%</p>
                </div>
                <p className="mt-1 text-[10px] text-muted">Track {match.trackId}</p>
                <p className="mt-1 text-[10px] text-muted">{new Date(match.timestamp).toLocaleString()}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
