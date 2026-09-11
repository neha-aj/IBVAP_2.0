import EvidenceCard from "./EvidenceCard";
import EvidenceDetail from "./EvidenceDetail";

export default function EvidenceList({ evidence, selectedEvidence, onSelect }) {
  if (evidence.length === 0) {
    return (
      <section className="panel p-10 text-center">
        <p className="text-sm font-semibold text-primary">
          No evidence recordings found
        </p>

        <p className="mt-1 text-xs text-muted">
          Clips are captured automatically for critical-severity events --
          try changing the search or filters, or check back shortly.
        </p>
      </section>
    );
  }

  return (
    <div className="space-y-3">
      {evidence.map((item) => {
        const selected = selectedEvidence?.id === item.id;
        return (
          // Expands right below the card that was clicked, not in a side
          // panel that (on anything narrower than the xl breakpoint) used
          // to stack below the *entire* list instead.
          <div key={item.id}>
            <EvidenceCard evidence={item} selected={selected} onSelect={onSelect} />
            {selected && <EvidenceDetail evidence={item} />}
          </div>
        );
      })}
    </div>
  );
}
