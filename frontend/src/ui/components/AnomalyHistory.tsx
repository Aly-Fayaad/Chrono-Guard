import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { DetectionResult, HealthMeasurement, MetricType } from "../../shared/types";
import { buildBaseline } from "../../anomaly/baseline";
import { METRICS } from "../config";
import { metStamp } from "../lib/time";
import { EmptyState } from "./EmptyState";
import { Panel } from "./Panel";
import { StatusBadge, DETECTION_BADGE } from "./StatusBadge";

/**
 * Newest-first list of currently flagged metrics with observed vs personal
 * baseline values, deviation score and a plain-language explanation.
 * Data-quality warnings are deliberately excluded here — they are shown on
 * the tiles instead, so a sensor problem never reads as a health event.
 */
export function AnomalyHistory({
  detections,
  series,
}: {
  detections: DetectionResult[];
  series: Record<MetricType, HealthMeasurement[]>;
}) {
  const flagged = detections.filter((d) => d.status === "anomaly");

  return (
    <Panel label="Anomaly history" bodyClassName="p-0">
      <div id="anomaly-history" className="scroll-mt-20">
        {flagged.length === 0 ? (
          <div className="p-4 sm:p-5">
            <EmptyState
              title="No anomalies in the current window"
              hint="All tracked vitals sit within your personal baseline range."
            />
          </div>
        ) : (
          <ul className="divide-y divide-hairline">
            {flagged.map((d) => {
              const rows = [...series[d.metric]].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
              const latest = rows.at(-1);
              const baseline = buildBaseline(rows.slice(0, -3));
              const badge = DETECTION_BADGE[d.status];
              const z = d.zScore ?? 0;
              const up = z >= 0;
              return (
                <li key={d.metric} className="p-4 sm:px-5">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                    <span
                      aria-hidden
                      className={`flex h-6 w-6 items-center justify-center rounded border ${
                        up ? "border-review/40 text-review" : "border-earth/40 text-earth"
                      }`}
                    >
                      {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                    </span>
                    <p className="text-[13px] font-medium text-moonlight">{METRICS[d.metric].label}</p>
                    <StatusBadge variant={badge.variant} label={badge.label} />
                    <span className="tnum ml-auto text-[12px] text-regolith">{metStamp(latest?.recordedAt ?? "")}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 pl-9 font-mono text-[12px]">
                    <span className="text-moonlight">
                      obs <span className="text-review">{latest?.value ?? "—"}</span>
                      <span className="text-regolith"> {METRICS[d.metric].unit}</span>
                    </span>
                    <span className="text-regolith">
                      base {baseline ? baseline.median.toFixed(1) : "—"}
                    </span>
                    <span className={up ? "text-review" : "text-earth"}>
                      dev {d.zScore !== undefined ? `${z >= 0 ? "+" : "−"}${Math.abs(z).toFixed(1)}σ` : "—"}
                    </span>
                  </div>
                  {d.event && (
                    <p className="mt-1.5 pl-9 text-[12px] leading-relaxed text-regolith">
                      {d.event.explanation}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Panel>
  );
}
