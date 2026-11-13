import type { HealthData } from "../hooks/useHealthData";

export function TodayPage({ health: _health }: { health: HealthData }) {
  return (
    <div className="p-6 text-sm text-regolith">
      Today dashboard — lands in the next deliverable.
    </div>
  );
}
