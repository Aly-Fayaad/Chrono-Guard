import { useCallback, useEffect, useState } from "react";
import { RotateCw, History, FlaskConical } from "lucide-react";
import type { MetricType } from "../../shared/types";
import { useHealth } from "../HealthContext";
import { METRICS, METRIC_ORDER, CREW_ID } from "../config";
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
import { Panel } from "../components/Panel";
import {
  getDashboardSummary,
  listCheckIns,
  reanalyze,
  listAssessments,
  type DashboardSummary,
  type ApiAssessment,
  type ApiCheckInListItem,
  type ReanalysisResult,
} from "../../api/client";

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

  // Dashboard 7-day summary
  const [dashSummary, setDashSummary] = useState<DashboardSummary | null>(null);
  const [dashLoading, setDashLoading] = useState(false);

  // Assessment history
  const [assessHistory, setAssessHistory] = useState<ApiAssessment[]>([]);
  const [assessLoading, setAssessLoading] = useState(false);
  const [showAssessHistory, setShowAssessHistory] = useState(false);
  const [reanalyzeResult, setReanalyzeResult] = useState<ReanalysisResult | null>(null);
  const [reanalyzeLoading, setReanalyzeLoading] = useState(false);
  const [reanalyzeError, setReanalyzeError] = useState<string | null>(null);

  // Recent check-ins
  const [recentCheckIns, setRecentCheckIns] = useState<ApiCheckInListItem[]>([]);
  const [checkInsLoading, setCheckInsLoading] = useState(false);
  const [showCheckIns, setShowCheckIns] = useState(false);

  // Load supplementary data once real data is available
  useEffect(() => {
    if (isMock || !data) return;
    setDashLoading(true);
    void getDashboardSummary(CREW_ID)
      .then(setDashSummary)
      .catch(() => setDashSummary(null))
      .finally(() => setDashLoading(false));
  }, [isMock, data]);

  const loadAssessHistory = useCallback(async () => {
    if (isMock) return;
    setAssessLoading(true);
    try {
      const page = await listAssessments(CREW_ID, 10, 0);
      setAssessHistory(page.items);
      setShowAssessHistory(true);
    } catch {
      /* silently ignore */
    } finally {
      setAssessLoading(false);
    }
  }, [isMock]);

  const loadCheckIns = useCallback(async () => {
    if (isMock) return;
    setCheckInsLoading(true);
    try {
      const page = await listCheckIns(CREW_ID, 5, 0);
      setRecentCheckIns(page.items);
      setShowCheckIns(true);
    } catch {
      /* silently ignore */
    } finally {
      setCheckInsLoading(false);
    }
  }, [isMock]);

  const triggerReanalyze = useCallback(async () => {
    if (isMock) return;
    setReanalyzeLoading(true);
    setReanalyzeError(null);
    try {
      const result = await reanalyze(CREW_ID);
      setReanalyzeResult(result);
      await refresh();
    } catch (cause) {
      setReanalyzeError(cause instanceof Error ? cause.message : "Re-analysis failed.");
    } finally {
      setReanalyzeLoading(false);
    }
  }, [isMock, refresh]);

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

            {/* 7-day dashboard stats under metric tiles */}
            {dashSummary && !dashLoading && (
              <Panel label="7-day metric summary" actions={<span className="tnum text-[11px] text-regolith">Last {dashSummary.window_days} days</span>}>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {dashSummary.measurements.map((m) => {
                    const metricKey = (
                      m.type === "body_temperature" ? "temperature" :
                      m.type === "heart_rate" ? "heart_rate" :
                      m.type === "hrv" ? "hrv" : m.type
                    ) as MetricType;
                    const displayLabel = METRICS[metricKey]?.label ?? m.type.replace(/_/g, " ");
                    return (
                      <div key={m.type} className="rounded-panel border border-hairline bg-panel p-3">
                        <p className="label-eyebrow">{displayLabel}</p>
                        <p className="tnum mt-1 text-[18px] font-medium text-moonlight">
                          {m.mean_7d !== null ? m.mean_7d.toFixed(1) : "—"}
                          <span className="ml-1 text-[11px] text-regolith">{m.unit}</span>
                        </p>
                        <p className="tnum mt-0.5 text-[11px] text-regolith">7-day mean · {m.valid_count_7d} reading{m.valid_count_7d !== 1 ? "s" : ""}</p>
                      </div>
                    );
                  })}
                </div>
                {dashSummary.data_freshness_hours !== null && (
                  <p className="mt-2 text-[11px] text-ink">
                    Data freshness: {dashSummary.data_freshness_hours.toFixed(1)} h since last reading.
                  </p>
                )}
              </Panel>
            )}

            {/* Assessment history + re-analyse */}
            {!isMock && (
              <Panel
                label="Assessment history"
                actions={
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => void triggerReanalyze()}
                      disabled={reanalyzeLoading}
                      className="motion-fade inline-flex min-h-[32px] items-center gap-1.5 rounded border border-earth/40 px-2.5 text-[11px] text-earth hover:bg-earth/10 disabled:opacity-40"
                      title="Re-analyse all check-ins with the current engine"
                    >
                      <FlaskConical size={12} aria-hidden />
                      {reanalyzeLoading ? "Running…" : "Re-analyse"}
                    </button>
                    <button
                      onClick={() => showAssessHistory ? setShowAssessHistory(false) : void loadAssessHistory()}
                      disabled={assessLoading}
                      className="motion-fade inline-flex min-h-[32px] items-center gap-1.5 rounded border border-hairline px-2.5 text-[11px] text-regolith hover:text-moonlight disabled:opacity-40"
                    >
                      <History size={12} aria-hidden />
                      {assessLoading ? "Loading…" : showAssessHistory ? "Hide" : "History"}
                    </button>
                  </div>
                }
              >
                {reanalyzeResult && (
                  <p className="mb-3 rounded border border-nominal/30 bg-nominal/5 px-3 py-2 text-[12px] text-nominal" role="status">
                    Re-analysis complete — {reanalyzeResult.succeeded} succeeded, {reanalyzeResult.failed} failed out of {reanalyzeResult.processed} check-ins.
                  </p>
                )}
                {reanalyzeError && (
                  <p className="mb-3 text-[12px] text-watch" role="alert">{reanalyzeError}</p>
                )}
                {showAssessHistory && assessHistory.length > 0 && (
                  <ul className="divide-y divide-hairline">
                    {assessHistory.map((a) => (
                      <li key={a.id} className="py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-[13px] font-medium text-moonlight capitalize">{a.status.replace(/_/g, " ")}</p>
                          <span className="tnum text-[11px] text-regolith">{metStamp(a.created_at)}</span>
                        </div>
                        <p className="mt-0.5 text-[12px] text-regolith">{a.summary}</p>
                      </li>
                    ))}
                  </ul>
                )}
                {showAssessHistory && assessHistory.length === 0 && (
                  <p className="text-[12px] text-regolith">No assessment records found.</p>
                )}
                {!showAssessHistory && !reanalyzeResult && !reanalyzeError && (
                  <p className="text-[12px] text-regolith">View past assessments or trigger a fresh analysis pass on stored check-ins.</p>
                )}
              </Panel>
            )}

            {/* Recent check-ins */}
            {!isMock && (
              <Panel
                label="Recent check-ins"
                actions={
                  <button
                    onClick={() => showCheckIns ? setShowCheckIns(false) : void loadCheckIns()}
                    disabled={checkInsLoading}
                    className="motion-fade inline-flex min-h-[32px] items-center gap-1.5 rounded border border-hairline px-2.5 text-[11px] text-regolith hover:text-moonlight disabled:opacity-40"
                  >
                    <History size={12} aria-hidden />
                    {checkInsLoading ? "Loading…" : showCheckIns ? "Hide" : "Show"}
                  </button>
                }
              >
                {showCheckIns && recentCheckIns.length > 0 ? (
                  <ul className="divide-y divide-hairline">
                    {recentCheckIns.map((ci) => (
                      <li key={ci.id} className="flex items-center justify-between py-2.5 text-[12px]">
                        <span className="tnum text-moonlight">{metStamp(ci.submitted_at)}</span>
                        {ci.notes && <span className="max-w-[60%] truncate text-regolith">{ci.notes}</span>}
                      </li>
                    ))}
                  </ul>
                ) : showCheckIns ? (
                  <p className="text-[12px] text-regolith">No check-ins recorded yet.</p>
                ) : (
                  <p className="text-[12px] text-regolith">Your 5 most recent check-in timestamps. Load to review.</p>
                )}
              </Panel>
            )}
          </>
        )}
      </div>
    </PageShell>
  );
}
