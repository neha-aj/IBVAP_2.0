import AlertCard from "./AlertCard";

export default function AlertList({
  alerts,
  selectedAlert,
  onSelect,
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
      {alerts.map((alert) => (
        <AlertCard
          key={alert.id}
          alert={alert}
          selected={selectedAlert?.id === alert.id}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}