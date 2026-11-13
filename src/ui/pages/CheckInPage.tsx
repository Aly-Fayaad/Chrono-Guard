import type { HealthData } from "../hooks/useHealthData";

export function CheckInPage({ health: _health }: { health: HealthData }) {
  return (
    <div className="p-6 text-sm text-regolith">
      Health check-in — lands in a later deliverable.
    </div>
  );
}
