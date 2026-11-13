import type { HealthData } from "../hooks/useHealthData";

export function GuidancePage({ health: _health }: { health: HealthData }) {
  return (
    <div className="p-6 text-sm text-regolith">
      Guidance & follow-up — lands in a later deliverable.
    </div>
  );
}
