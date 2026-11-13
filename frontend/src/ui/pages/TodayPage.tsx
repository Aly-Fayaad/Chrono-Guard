import { useCallback, useState } from "react";
import { RotateCw } from "lucide-react";
import type { MetricType } from "../../shared/types";
import { useHealth } from "../HealthContext";
import { METRICS, METRIC_ORDER } from "../config";
import { metStamp } from "../lib/time";
import { useNow } from "../hooks/useNow";
import { DETECTION_BADGE } from "../components/StatusBadge";
import { FatiguePanel } from "../components/FatiguePanel";
import { MetricTile } from "../components/MetricTile";
import { AnomalyHistory } from "../components/AnomalyHistory";
import { TaskStrip } from "../components/TaskStrip";
import { BaselineChartPanel } from "../components/BaselineChartPanel";
import { TrendView } from "../components/TrendView";
import { EmptyState } from "../components/EmptyState";
import { PanelSkeleton, Skeleton } from "../components/Skeleton";
import { PageShell } from "../shell/PageShell";
import { MOOD } from "../shell/mood";
import { EarthOrbitGauge } from "../components/EarthOrbitGauge";

/**
 * Today — the operational dashboard, reached from the Hub's Earth body.
 * Same features as before (crew status, reason list, metric tiles,
 * baseline chart, trend view, anomalies, next task) inside the new shell.
 */
export function TodayPage() {
  const health = useHealth();
  const { data, refresh, error, isMock } = health;
  const [metric, setMetric] = useState<MetricType>("heart_rate");
  const [demoError, setDemoError] = useState<string | null>(null);
  const now = useNow(30_000);

  const loadDemo = useCallback(async () => {
    setDemoError(null);
    try {
      await health.seedDemo();
    } catch (cause) {
      setDemoError(
        cause instanceof Error ? cause.message : "The demo dataset could not be loaded.",
      );
    }
  }, [health]);

  const mood = data ? MOOD[data.assessment.status] : null;

  return (
    <PageShell title="Today" crumb="Earth" bodyName="Earth">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="label-eyebrow">Earth · Home &amp; baseline</p>
            <h1 className="font-display mt-0.5 text-[22px] font-medium text-moonlight">Today</h1>
            <p className="tnum mt-0.5 text-[12px] text-regolith">
              CREW DEMO-01 · {metStamp(now)}
              {mood && (
                <>
                  {" · "}
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: mood.accent }} />
                    <span style={{ color: mood.accent }}>{mood.label}</span>
                  </span>
                </>
              )}
            </p>
          </div>
        </div>

        {error && (
          <EmptyState
            title={data ? "Couldn't refresh health data" : "Couldn't load health data"}
            hint={demoError ?? error}
            action={
              <div className="mt-2 flex flex-wrap justify-center gap-2">
                <button
                  onClick={() => void refresh()}
                  className="motion-fade inline-flex min-h-[44px] items-center gap-2 rounded border border-earth/40 px-3 text-[12px] text-earth hover:bg-earth/10"
                >
                  <RotateCw size={13} aria-hidden /> Retry
                </button>
                {!isMock && (
                  <button
                    onClick={() => void loadDemo()}
                    className="motion-fade inline-flex min-h-[44px] items-center rounded border border-hairline px-3 text-[12px] text-regolith hover:text-moonlight"
                  >
                    Load demo data
                  </button>
                )}
              </div>
            }
          />
        )}

        {!error && !data && (
          <div className="space-y-4">
            <PanelSkeleton rows={3} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {METRIC_ORDER.map((m) => (
                <div key={m} className="glass rounded-panel p-4">
                  <Skeleton className="h-3 w-16" />
                  <Skeleton className="mt-3 h-7 w-20" />
                  <Skeleton className="mt-3 h-7 w-full" />
                </div>
              ))}
            </div>
            {!isMock && (
              <EmptyState
                title="No readings yet"
                hint={
                  demoError ??
                  "Log a check-in, or load a demo dataset so the backend can run its analysis."
                }
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
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_1fr]">
              <div className="glass rounded-panel p-5">
                <EarthOrbitGauge status={data.assessment.status} />
                <p className="mt-3 text-center text-[11px] text-ink">
                  A small echo of the Hub: your status, carried by an orbit.
                </p>
              </div>
              <FatiguePanel a={data.assessment} />
            </div>

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

            <BaselineChartPanel metric={metric} series={data.series[metric] ?? []} detection={data.detections.find((d) => d.metric === metric) ?? { metric, status: "insufficient_baseline", reason: "No data for this metric." }} />

            <TrendView detections={data.detections} series={data.series} selected={metric} onSelect={setMetric} />

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
              <AnomalyHistory detections={data.detections} series={data.series} />
              <TaskStrip tasks={data.tasks} wake={health.wake} />
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}
