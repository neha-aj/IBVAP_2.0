import { Search } from "lucide-react";

export default function CameraFilters({
  search,
  setSearch,
  status,
  setStatus,
  sector,
  setSector,
}) {
  return (
    <section className="panel mb-5 flex flex-wrap items-center gap-3 p-3">
      <label className="relative min-w-52 flex-1">
        <Search
          className="absolute left-3 top-2.5 text-muted"
          size={15}
        />

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search cameras..."
          className="w-full border bg-panelSecondary py-2 pl-9 pr-3 text-xs text-primary outline-none placeholder:text-muted focus:border-info"
        />
      </label>

      <select
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        className="border bg-panelSecondary p-2 text-xs text-secondary outline-none focus:border-info"
      >
        <option value="all">All statuses</option>
        <option value="online">Online</option>
        <option value="warning">Warning</option>
        <option value="offline">Offline</option>
      </select>

      <select
        value={sector}
        onChange={(e) => setSector(e.target.value)}
        className="border bg-panelSecondary p-2 text-xs text-secondary outline-none focus:border-info"
      >
        <option value="all">All sectors</option>
        <option value="Alpha">Alpha</option>
        <option value="Bravo">Bravo</option>
        <option value="Charlie">Charlie</option>
        <option value="Delta">Delta</option>
        <option value="Echo">Echo</option>
        <option value="Foxtrot">Foxtrot</option>
        <option value="Golf">Golf</option>
        <option value="Hotel">Hotel</option>
      </select>
    </section>
  );
}