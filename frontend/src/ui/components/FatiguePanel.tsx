import { Info } from "lucide-react";
import type { FatigueAssessment } from "../../shared/types";
import { ArcGauge } from "./ArcGauge";
import { Panel } from "./Panel";
import { ReasonList } from "./ReasonList";
import { StatusBadge, FATIGUE_BADGE } from "./StatusBadge";
import { Skeleton } from "./Skeleton";

function scrollTo(id: string) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

/**
 * Fatigue assessment panel. Always carries the non-diagnostic footnote;
 * updates are announced politely to screen readers.
 */
export function FatiguePanel({ a, loading }: { a: FatigueAssessment; loading?: boolean }) {
  const badge = FATIGUE_BADGE[a.status];
  return (
    <Panel label="Crew status">
      <div aria-live="polite">
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            <ArcGauge status={a.status} label="Fatigue assessment" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[15px] font-medium text-moonlight">{badge.label}</h3>
                <StatusBadge variant={badge.variant} label={badge.label} />
              </div>
              <p className="label-eyebrow mt-4">Why was this flagged?</p>
              <div className="mt-2">
                <ReasonList reasons={a.reasons} />
              </div>
              {a.status !== "insufficient_data" && (
                <button
                  onClick={() => scrollTo("anomaly-history")}
                  className="motion-fade mt-4 inline-flex min-h-[44px] items-center rounded border border-earth/40 px-3 text-[12px] text-earth hover:bg-earth/10"
                >
                  See related anomalies ↓
                </button>
              )}
            </div>
          </div>
        )}
        <p className="mt-4 flex items-center gap-1.5 border-t border-hairline pt-3 text-[11px] text-ink">
          <Info size={12} aria-hidden />
          Potential concern for human review. Not a diagnosis.
        </p>
      </div>
    </Panel>
  );
}
