import type { DetectionResult, HealthMeasurement, MetricType } from "../../shared/types";
import { METRICS, METRIC_ORDER } from "../config";
import { Panel } from "./Panel";
import { Sparkline } from "./Sparkline";
import { DETECTION_BADGE, StatusBadge } from "./StatusBadge";

const SPARK_COLOR: Record<string, string> = {
  nominal: "#3DD6B0",
  watch: "#F2B84B",
  review: "#F26B3A",
  insufficient: "#6B7684",
  quality: "#6B7684",
};

/**
 * Trend view: small-multiple sparklines for all four metrics, with the
 * sustained-change window highlighted where a sustained anomaly was flagged.
 * Clicking a tile selects that metric for the main chart.
 */
export function TrendView({
  detections,
  series,
  selected,
  onSelect,
}: {
  detections: DetectionResult[];
  series: Record<MetricType, HealthMeasurement[]>;
  selected: MetricType;
  onSelect: (m: MetricType) => void;
}) {
  return (
    <Panel label="Trend view — last 17 days">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {METRIC_ORDER.map((m) => {
          const detection = detections.find((d) => d.metric === m);
          const badge = detection ? DETECTION_BADGE[detection.status] : null;
          const rows = [...series[m]].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
          const values = rows.filter((x) => x.quality === "valid").map((x) => x.value);
          const highlight =
            detection?.event?.kind === "sustained" ? 3 : 0;
          const latest = rows.at(-1)?.value;
          return (
            <button
              key={m}
              onClick={() => onSelect(m)}
              aria-pressed={selected === m}
              className={`motion-fade rounded-panel border p-3 text-left ${
                selected === m ? "border-earth/70 bg-raised" : "border-hairline bg-panel hover:border-regolith/40"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="label-eyebrow">{METRICS[m].label}</p>
                <span className="tnum text-[12px] text-moonlight">
                  {latest ?? "—"}
                  <span className="text-regolith"> {METRICS[m].unit}</span>
                </span>
              </div>
              <div className="mt-2">
                <Sparkline
                  values={values}
                  color={SPARK_COLOR[badge?.variant ?? "insufficient"] ?? "#6B7684"}
                  highlightWindow={highlight}
                  label={`${METRICS[m].label} trend sparkline`}
                  className="h-9 w-full"
                />
              </div>
              {badge && (
                <div className="mt-2">
                  <StatusBadge variant={badge.variant} label={badge.label} />
                </div>
              )}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
