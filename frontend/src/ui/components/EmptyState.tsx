import type { ReactNode } from "react";
import { CircleDashed } from "lucide-react";

/** Dashed empty/loading placeholder with optional action. */
export function EmptyState({
  title,
  hint,
  action,
  hatched,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  hatched?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 rounded-panel border border-dashed border-regolith/30 px-6 py-10 text-center ${
        hatched ? "hatch" : ""
      }`}
    >
      <CircleDashed size={20} aria-hidden className="text-ink" />
      <p className="text-sm text-moonlight">{title}</p>
      {hint && <p className="max-w-sm text-xs text-regolith">{hint}</p>}
      {action}
    </div>
  );
}
