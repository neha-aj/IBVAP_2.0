import AlertCard from "./AlertCard";
import AlertDetails from "./AlertDetails";

export default function AlertList({
  alerts,
  selectedAlert,
  onSelect,
  onAcknowledge,
  onResolve,
  onViewCamera,
}) {
  if (alerts.length === 0) {
    return (
      <section className="panel p-10 text-center">
        <p className="text-sm font-semibold text-primary">
          No alerts found
        </p>

        <p className="mt-1 text-xs text-muted">
          Try changing the search or filters.
        </p>
      </section>
    );
  }

  return (
    <div className="space-y-3">
      {alerts.map((alert) => {
        const selected = selectedAlert?.id === alert.id;
        return (
          // Expands right below the card that was clicked, not in a side
          // panel that (on anything narrower than the xl breakpoint) used
          // to stack below the *entire* list instead.
          <div key={alert.id}>
            <AlertCard alert={alert} selected={selected} onSelect={onSelect} />
            {selected && (
              <AlertDetails
                alert={alert}
                onAcknowledge={onAcknowledge}
                onResolve={onResolve}
                onViewCamera={onViewCamera}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
