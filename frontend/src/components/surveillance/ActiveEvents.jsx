import { Circle, TriangleAlert } from "lucide-react";

export default function ActiveEvents({ camera }) {
  const events = camera.alert
    ? [
        {
          name: camera.alert,
          time: "2 minutes ago",
          critical: true,
        },
        {
          name: "Person Detected",
          time: "4 minutes ago",
        },
        {
          name: "Vehicle Detected",
          time: "7 minutes ago",
        },
      ]
    : [
        {
          name: "Person Detected",
          time: "3 minutes ago",
        },
        {
          name: "Vehicle Detected",
          time: "8 minutes ago",
        },
      ];

  return (
    <section className="panel p-4">
      <p className="eyebrow">Active Events</p>

      <div className="mt-3 space-y-3">
        {events.map((event) => (
          <div className="flex gap-2" key={event.name}>
            <div
              className={
                event.critical ? "text-danger" : "text-info"
              }
            >
              {event.critical ? (
                <TriangleAlert size={15} />
              ) : (
                <Circle
                  size={10}
                  className="mt-0.5 fill-current"
                />
              )}
            </div>

            <div>
              <p
                className={`text-xs font-medium ${
                  event.critical
                    ? "text-danger"
                    : "text-primary"
                }`}
              >
                {event.name}
              </p>

              <p className="mt-1 text-[11px] text-muted">
                {camera.name} · {event.time}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}