import { useCallback, useState } from "react";
import { RotateCw } from "lucide-react";
import type { MetricType } from "../../shared/types";
import { seedDemo } from "../../data/seed";
import type { HealthData } from "../hooks/useHealthData";
import { METRICS, METRIC_ORDER } from "../config";
import { metStamp } from "../lib/time";
import { useNow } from "../hooks/useNow";
import { DETECTION_BADGE } from "../components/StatusBadge";
import { FatiguePanel } from "../components/FatiguePanel";
import { MetricTile } from "../components/MetricTile";
import { AnomalyHistory } from "../components/AnomalyHistory";
import { TaskStrip } from "../components/TaskStrip";
import { Panel } from "../components/Panel";
import { SectionHeader } from "../components/SectionHeader";
import { EmptyState } from "../components/EmptyState";
import { PanelSkeleton, Skeleton } from "../components/Skeleton";

export function TodayPage({ health }: { health: HealthData }) {
  const { data, refresh, error, isMock } = health;
  const [metric, setMetric] = useState<MetricType>("heart_rate");
  const now = useNow(30_000);

  const loadDemo = useCallback(async () => {
    await seedDemo("normal");
    await refresh();
  }, [refresh]);

  return (
    <div className="space-y-4">
      <SectionHeader
        eyebrow="Deck A — Health"
        title="Today"
        meta={`CREW DEMO-01 · ${metStamp(now)}Z`}
      />

      {error && (
        <EmptyState
          title="Couldn't load health data"
          hint={error}
          action={
            <button
              onClick={() => void refresh()}
              className="motion-fade mt-2 inline-flex min-h-[44px] items-center gap-2 rounded border border-earth/40 px-3 text-[12px] text-earth hover:bg-earth/10"
            >
              <RotateCw size={13} aria-hidden /> Retry
            </button>
          }
        />
      )}

      {!error && !data && (
        <div className="space-y-4">
          <PanelSkeleton rows={3} />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {METRIC_ORDER.map((m) => (
              <div key={m} className="rounded-panel border border-hairline bg-panel p-4">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="mt-3 h-7 w-20" />
                <Skeleton className="mt-3 h-7 w-full" />
              </div>
            ))}
          </div>
          {!isMock && (
            <EmptyState
              title="No readings yet"
              hint="Log a check-in, or load a demo dataset to explore the console."
              action={
                <button
                  onClick={() => void loadDemo()}
                  className="motion-fade mt-2 inline-flex min-h-[44px] items-center gap-2 rounded border border-earth/40 px-3 text-[12px] text-earth hover:bg-earth/10"
                >
                  Load demo data
                </button>
              }
            />
          )}
        </div>
      )}

      {data && (
        <>
          <FatiguePanel a={data.assessment} />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {data.detections.map((d) => {
              const rows = [...data.series[d.metric]].sort((a, b) =>
                a.recordedAt.localeCompare(b.recordedAt),
              );
              const latest = rows.at(-1);
              const validSpark = rows.filter((m) => m.quality === "valid").slice(-10).map((m) => m.value);
              const badge = DETECTION_BADGE[d.status];
              return (
                <MetricTile
                  key={d.metric}
                  label={METRICS[d.metric].label}
                  unit={METRICS[d.metric].unit}
                  value={latest?.value ?? null}
                  spark={validSpark}
                  statusVariant={badge.variant}
                  statusLabel={badge.label}
                  selected={metric === d.metric}
                  onSelect={() => setMetric(d.metric)}
                  hatched={d.status === "data_quality"}
                  ariaLabel={`${METRICS[d.metric].label}: ${latest?.value ?? "no data"} ${METRICS[d.metric].unit}, ${badge.label}. Select to view chart.`}
                />
              );
            })}
          </div>

          <Panel label={`Baseline — ${METRICS[metric].label}`} actions={<span className="tnum text-[11px] text-regolith">17-day window</span>}>
            <p className="text-sm text-regolith">
              Chart view lands in the next deliverable — metric “{METRICS[metric].label}” selected.
            </p>
          </Panel>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
            <AnomalyHistory detections={data.detections} series={data.series} />
            <TaskStrip tasks={data.tasks} wake={health.wake} />
          </div>
        </>
      )}
    </div>
  );
}
