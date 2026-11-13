import type { HealthData } from "../hooks/useHealthData";

export function SchedulePage({ health: _health }: { health: HealthData }) {
  return (
    <div className="p-6 text-sm text-regolith">
      Mission schedule — lands in a later deliverable.
    </div>
  );
}
