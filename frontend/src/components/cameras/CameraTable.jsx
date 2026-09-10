import { MoreVertical, Settings2 } from "lucide-react";
import Badge from "../common/Badge";
import StatusDot from "../common/StatusDot";

export default function CameraTable({ cameras, onSelect }) {
  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <p className="eyebrow">Camera Inventory</p>
        <p className="mt-1 text-[11px] text-secondary">
          Manage deployed surveillance devices and their health status
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[800px] text-left">
          <thead>
            <tr className="border-b border-line bg-panelSecondary">
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted">
                Camera
              </th>

              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted">
                Location
              </th>

              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted">
                Sector
              </th>

              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted">
                Status
              </th>

              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted">
                Resolution
              </th>

              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted">
                FPS
              </th>

              <th className="px-4 py-3 text-right text-[10px] uppercase tracking-wider text-muted">
                Actions
              </th>
            </tr>
          </thead>

          <tbody>
            {cameras.map((camera) => (
              <tr
                key={camera.id}
                onClick={() => onSelect(camera)}
                className="cursor-pointer border-b border-line last:border-0 hover:bg-panelSecondary/60"
              >
                <td className="px-4 py-4">
                  <div className="flex items-center gap-3">
                    <StatusDot status={camera.status} />

                    <div>
                      <p className="text-xs font-semibold text-primary">
                        {camera.name}
                      </p>

                      <p className="mt-1 font-mono text-[10px] text-muted">
                        {camera.id}
                      </p>
                    </div>
                  </div>
                </td>

                <td className="px-4 py-4 text-xs text-secondary">
                  {camera.location}
                </td>

                <td className="px-4 py-4">
                  <span className="text-xs text-secondary">
                    {camera.sector}
                  </span>
                </td>

                <td className="px-4 py-4">
                  <Badge tone={camera.status}>
                    {camera.status}
                  </Badge>
                </td>

                <td className="px-4 py-4 font-mono text-xs text-secondary">
                  {camera.resolution}
                </td>

                <td className="px-4 py-4 font-mono text-xs text-secondary">
                  {camera.fps}
                </td>

                <td className="px-4 py-4">
                  <div className="flex justify-end gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(camera);
                      }}
                      aria-label={`Configure ${camera.name}`}
                      className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
                    >
                      <Settings2 size={15} />
                    </button>

                    <button
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`More options for ${camera.name}`}
                      className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
                    >
                      <MoreVertical size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {cameras.length === 0 && (
        <div className="px-4 py-12 text-center">
          <p className="text-sm text-primary">No cameras found</p>
          <p className="mt-1 text-xs text-muted">
            Try changing the search or filters.
          </p>
        </div>
      )}
    </section>
  );
}