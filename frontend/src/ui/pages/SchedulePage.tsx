import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, TriangleAlert, Trash2, AlertTriangle, Lightbulb, ChevronDown, ChevronUp, RotateCw } from "lucide-react";
import type { MissionTask } from "../../shared/types";
import { useHealth } from "../HealthContext";
import type { TaskInput } from "../hooks/useHealthData";
import { metDay, metStamp, hoursBetween, missionDayStart, missionHour } from "../lib/time";
import { useNow } from "../hooks/useNow";
import { Panel } from "../components/Panel";
import { PageShell } from "../shell/PageShell";
import { CircadianArcs } from "../components/CircadianArcs";
import { CREW_ID } from "../config";
import {
  getMissionConflicts,
  getMissionRecommendations,
  deleteTask,
  type JsonObject,
} from "../../api/client";

const WINDOW_H = 48;
const WAKE_WARNING_H = 14;

const inputCls =
  "tnum motion-fade w-full rounded-panel border border-hairline bg-raised px-3 py-2 text-[13px] text-moonlight placeholder:text-ink focus:border-earth/60 focus:outline-none";

/** Assign tasks to overlapping lanes so blocks never collide. */
function laneAssign(tasks: MissionTask[]): MissionTask[][] {
  const sorted = [...tasks].sort((a, b) => a.startsAt.localeCompare(b.startsAt));
  const lanes: MissionTask[][] = [];
  for (const t of sorted) {
    const lane = lanes.find((l) => Date.parse(l.at(-1)!.endsAt) <= Date.parse(t.startsAt));
    if (lane) lane.push(t);
    else lanes.push([t]);
  }
  return lanes;
}

// ----- Mission-intel types (subset of what the API returns) -----
interface ConflictItem {
  conflict_id: string;
  rule_id: string;
  severity: string;
  message: string;
  task_ids: string[];
}

interface RecommendationItem {
  recommendation_id: string;
  title: string;
  rationale: string;
  priority: string;
}

export function SchedulePage() {
  const health = useHealth();
  const { data, wake } = health;
  const now = useNow(30_000);
  const [form, setForm] = useState({ title: "", start: "", hours: "2", demand: "routine" as MissionTask["demand"] });
  const [formError, setFormError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState(false);

  // Mission-intel state
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [intelLoading, setIntelLoading] = useState(false);
  const [intelError, setIntelError] = useState<string | null>(null);
  const [showRecs, setShowRecs] = useState(false);

  // Task delete state
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadIntel = useCallback(async () => {
    setIntelLoading(true);
    setIntelError(null);
    try {
      const [cRes, rRes] = await Promise.all([
        getMissionConflicts(CREW_ID),
        getMissionRecommendations(CREW_ID),
      ]);
      const cData = cRes as JsonObject;
      const rData = rRes as JsonObject;
      setConflicts((cData.conflicts as ConflictItem[] | undefined) ?? []);
      setRecommendations((rData.recommendations as RecommendationItem[] | undefined) ?? []);
    } catch (cause) {
      setIntelError(cause instanceof Error ? cause.message : "Could not load mission intel.");
    } finally {
      setIntelLoading(false);
    }
  }, []);

  // Reload conflicts/recommendations whenever task list changes
  useEffect(() => {
    void loadIntel();
  }, [loadIntel, data?.tasks]);

  const handleDelete = useCallback(
    async (taskId: string) => {
      setDeletingId(taskId);
      setDeleteError(null);
      try {
        await deleteTask(CREW_ID, taskId);
        await health.refresh();
      } catch (cause) {
        setDeleteError(cause instanceof Error ? cause.message : "Could not delete task.");
      } finally {
        setDeletingId(null);
      }
    },
    [health],
  );

  // Map task IDs → conflict messages for quick lookup
  const conflictByTask = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const c of conflicts) {
      for (const tid of c.task_ids) {
        (map[tid] ??= []).push(c.message);
      }
    }
    return map;
  }, [conflicts]);

  const windowStart = useMemo(() => missionDayStart(now), [now]);

  const tasks = data?.tasks ?? [];
  const pct = (iso: string) =>
    Math.min(100, Math.max(0, ((Date.parse(iso) - windowStart.getTime()) / (WINDOW_H * 3_600_000)) * 100));
  const inWindow = tasks.filter((t) => Date.parse(t.endsAt) > windowStart.getTime() && Date.parse(t.startsAt) < windowStart.getTime() + WINDOW_H * 3_600_000);
  const lanes = laneAssign(inWindow);

  const nowPct = pct(now.toISOString());
  const wakePct = wake ? pct(wake) : null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = form.title.trim();
    if (!title || !form.start) {
      setFormError("Add a title and a start time.");
      return;
    }
    const s = new Date(form.start);
    const hours = Math.max(0.5, Number(form.hours) || 2);
    const task: TaskInput = {
      title,
      startsAt: s.toISOString(),
      endsAt: new Date(s.getTime() + hours * 3_600_000).toISOString(),
      demand: form.demand,
    };
    setFormError(null);
    try {
      await health.saveTask(task);
    } catch (cause) {
      setFormError(
        cause instanceof Error ? cause.message : "The task could not be saved.",
      );
      return;
    }
    setForm({ ...form, title: "" });
    setSavedMsg(true);
    window.setTimeout(() => setSavedMsg(false), 3000);
  };
  return (
    <PageShell title="Schedule" crumb="Sun" bodyName="Sun">
      <div className="space-y-4">
        <div>
          <p className="label-eyebrow">Sun · Circadian rhythm &amp; time</p>
          <h1 className="font-display mt-0.5 text-[22px] font-medium text-moonlight">Mission schedule</h1>
          <p className="tnum mt-0.5 text-[12px] text-regolith">
            48-hour planning window · task blocks show demand level
          </p>
        </div>

        <Panel
          label="Circadian light guidance"
          actions={<span className="tnum text-[11px] text-regolith">Earth 24 h clock · 06:30 → 21:30 light</span>}
        >
          <CircadianArcs now={now} wake={wake} />
          <p className="mt-3 text-[12px] leading-relaxed text-regolith">
            The amber arc is the recommended <span className="text-sun">bright-light window</span>; the
            shadowed arc is the recommended <span className="text-silver">dark / sleep window</span>.
            Anchoring demanding tasks and meals inside the light arc helps your rhythm stay
            aligned to the published 24 h Earth clock; mission labels use the 24.65 h
            operational day.
          </p>
        </Panel>

        <Panel
          label="48-hour timeline"
          actions={<span className="tnum text-[11px] text-regolith">{metStamp(windowStart)} → +{WINDOW_H}h</span>}
        >
          {/* Visual timeline (list below is the accessible source of truth) */}
          <div
            role="img"
            aria-label={`48-hour mission timeline from ${metStamp(windowStart)}. ${inWindow.length} tasks scheduled. See the list below for details.`}
            aria-hidden={inWindow.length === 0 ? undefined : true}
            className="overflow-x-auto"
          >
            <div className="min-w-[720px]">
              {/* Hour scale */}
              <div className="relative mb-1 h-5">
                {Array.from({ length: WINDOW_H / 6 + 1 }).map((_, i) => {
                  const t = new Date(windowStart.getTime() + i * 6 * 3_600_000);
                  return (
                    <span
                      key={i}
                      className="tnum absolute top-0 text-[10px] text-regolith"
                      style={{ left: `${(i * 6 / WINDOW_H) * 100}%`, transform: i === WINDOW_H / 6 ? "translateX(-100%)" : undefined }}
                    >
                      {metDay(t)} {String(Math.floor(missionHour(t))).padStart(2, "0")}:00
                    </span>
                  );
                })}
              </div>

              <div className="relative rounded-panel border border-hairline bg-panel">
                {/* vertical gridlines every 6h */}
                <div aria-hidden className="absolute inset-0">
                  {Array.from({ length: WINDOW_H / 6 }).map((_, i) => (
                    <span
                      key={i}
                      className="absolute inset-y-0 w-px bg-hairline"
                      style={{ left: `${((i + 1) * 6 / WINDOW_H) * 100}%` }}
                    />
                  ))}
                </div>

                {/* awake band + wake marker + now marker */}
                {wake && (
                  <>
                    <div
                      aria-hidden
                      className="absolute inset-y-0 border-l border-dashed border-nominal/50"
                      style={{ left: `${wakePct}%` }}
                      title="Last wake"
                    />
                    <div
                      aria-hidden
                      className="absolute inset-y-0 right-0 bg-nominal/[0.04]"
                      style={{ left: `${wakePct}%` }}
                    />
                  </>
                )}
                {nowPct >= 0 && nowPct <= 100 && (
                  <div
                    aria-hidden
                    className="absolute inset-y-0 z-10 border-l border-dashed border-earth/70"
                    style={{ left: `${nowPct}%` }}
                  />
                )}

                {/* task lanes */}
                <div className="relative space-y-1.5 p-2">
                  {lanes.map((lane, li) => (
                    <div key={li} className="relative h-11">
                      {lane.map((t) => {
                        const left = pct(t.startsAt);
                        const width = Math.max(2, ((Date.parse(t.endsAt) - Date.parse(t.startsAt)) / (WINDOW_H * 3_600_000)) * 100);
                        const demanding = t.demand === "demanding";
                        const awakeH = wake ? hoursBetween(wake, t.startsAt) : null;
                        return (
                          <div
                            key={t.id}
                            className={`absolute inset-y-0 flex min-w-max items-center gap-2 rounded border px-2 font-mono text-[11px] ${
                              demanding
                                ? "border-review/70 bg-review/[0.07] text-review"
                                : "border-hairline bg-raised text-regolith"
                            }`}
                            style={{ left: `${left}%`, width: `${width}%` }}
                            title={`${t.title} · ${metStamp(t.startsAt)} · ${t.demand}${awakeH !== null && demanding ? ` · awake ${awakeH} h` : ""}`}
                          >
                            <span className="truncate">{t.title}</span>
                            {demanding && awakeH !== null && awakeH >= WAKE_WARNING_H && (
                              <span className="hidden shrink-0 text-watch sm:inline">awake {awakeH}h</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ))}
                  {!inWindow.length && (
                    <div className="p-6 text-center text-[12px] text-regolith">
                      No tasks inside the current 48-hour window.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Panel>

        {/* Mission conflicts */}
        {conflicts.length > 0 && (
          <Panel
            label="Mission conflicts"
            actions={
              <button
                onClick={() => void loadIntel()}
                disabled={intelLoading}
                className="motion-fade inline-flex items-center gap-1 text-[11px] text-regolith hover:text-moonlight disabled:opacity-40"
                aria-label="Refresh mission intel"
              >
                <RotateCw size={12} aria-hidden />
              </button>
            }
          >
            <ul className="space-y-2">
              {conflicts.map((c) => (
                <li key={c.conflict_id} className="flex items-start gap-2 rounded border border-review/30 bg-review/5 p-3">
                  <AlertTriangle size={14} aria-hidden className="mt-0.5 shrink-0 text-review" />
                  <div>
                    <p className="text-[12px] font-medium text-review">{c.rule_id.replace(/_/g, " ")}</p>
                    <p className="mt-0.5 text-[12px] text-regolith">{c.message}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-ink">Advisory only. Consult the flight surgeon for schedule changes.</p>
          </Panel>
        )}

        {/* Mission recommendations */}
        {recommendations.length > 0 && (
          <Panel
            label={`Recommendations (${recommendations.length})`}
            actions={
              <button
                onClick={() => setShowRecs((v) => !v)}
                className="motion-fade inline-flex items-center gap-1 text-[11px] text-regolith hover:text-moonlight"
                aria-expanded={showRecs}
              >
                {showRecs ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {showRecs ? "Hide" : "Show"}
              </button>
            }
          >
            {showRecs ? (
              <ul className="space-y-2">
                {recommendations.map((r) => (
                  <li key={r.recommendation_id} className="flex items-start gap-2 rounded border border-earth/30 bg-earth/5 p-3">
                    <Lightbulb size={14} aria-hidden className="mt-0.5 shrink-0 text-earth" />
                    <div>
                      <p className="text-[12px] font-medium text-moonlight">{r.title}</p>
                      <p className="mt-0.5 text-[12px] text-regolith">{r.rationale}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-regolith">
                {recommendations.length} advisory suggestion{recommendations.length !== 1 ? "s" : ""} available. Expand to review.
              </p>
            )}
          </Panel>
        )}

        {intelError && (
          <p className="text-[11px] text-watch" role="alert">{intelError}</p>
        )}

        <Panel label="Add task">
          <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_auto_auto_auto]">
            <input
              className={inputCls}
              placeholder="Task title (e.g. EVA sampling)"
              aria-label="Task title"
              value={form.title}
              onChange={(e) => { setForm({ ...form, title: e.target.value }); setFormError(null); }}
            />
            <input
              className={inputCls}
              type="datetime-local"
              aria-label="Start time"
              value={form.start}
              onChange={(e) => { setForm({ ...form, start: e.target.value }); setFormError(null); }}
            />
            <input
              className={inputCls}
              type="number"
              min={0.5}
              step={0.5}
              aria-label="Duration in hours"
              value={form.hours}
              onChange={(e) => setForm({ ...form, hours: e.target.value })}
            />
            <select
              className={inputCls}
              aria-label="Demand level"
              value={form.demand}
              onChange={(e) => setForm({ ...form, demand: e.target.value as MissionTask["demand"] })}
            >
              <option value="routine">Routine</option>
              <option value="demanding">Demanding</option>
            </select>
            <button
              type="submit"
              className="motion-fade inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-panel border border-earth/50 bg-earth/10 px-4 text-[13px] font-medium text-earth hover:bg-earth/20"
            >
              <Plus size={14} aria-hidden /> Add task
            </button>
            {formError && (
              <p className="text-[11px] text-review sm:col-span-5" role="alert">{formError}</p>
            )}
            {savedMsg && (
              <p className="text-[11px] text-nominal sm:col-span-5" role="status">Task saved to the mission server.</p>
            )}
          </form>
        </Panel>

        <Panel label="Task list" bodyClassName="p-0">
          {deleteError && (
            <p className="border-b border-hairline px-5 py-2 text-[11px] text-watch" role="alert">{deleteError}</p>
          )}
          <ul className="divide-y divide-hairline">
            {tasks.map((t) => {
              const demanding = t.demand === "demanding";
              const awakeH = wake ? hoursBetween(wake, t.startsAt) : null;
              const conflict = demanding && awakeH !== null && awakeH >= WAKE_WARNING_H;
              const taskConflicts = conflictByTask[t.id] ?? [];
              return (
                <li key={t.id} className="p-4 sm:px-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-moonlight">{t.title}</p>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[11px] ${
                          demanding ? "border-review/45 text-review" : "border-hairline text-regolith"
                        }`}
                      >
                        {demanding ? "DEMANDING" : "ROUTINE"}
                      </span>
                      <button
                        onClick={() => void handleDelete(t.id)}
                        disabled={deletingId === t.id}
                        className="motion-fade inline-flex min-h-[32px] items-center justify-center rounded border border-hairline px-2 text-regolith hover:border-review/50 hover:text-review disabled:opacity-40"
                        aria-label={`Delete task ${t.title}`}
                        title="Delete task"
                      >
                        <Trash2 size={13} aria-hidden />
                      </button>
                    </div>
                  </div>
                  <p className="tnum mt-1 text-[12px] text-regolith">
                    {metStamp(t.startsAt)} → {metStamp(t.endsAt)}
                    {awakeH !== null && ` · awake ${awakeH} h at start`}
                  </p>
                  {conflict && (
                    <p role="status" className="mt-1.5 flex items-center gap-1.5 text-[11px] text-watch">
                      <TriangleAlert size={12} aria-hidden /> Long wake period before a demanding task.
                    </p>
                  )}
                  {taskConflicts.map((msg, mi) => (
                    <p key={mi} className="mt-1.5 flex items-center gap-1.5 text-[11px] text-review">
                      <AlertTriangle size={12} aria-hidden /> {msg}
                    </p>
                  ))}
                </li>
              );
            })}
            {!tasks.length && (
              <li className="p-5 text-[12px] text-regolith">
                No tasks scheduled. Add one above — entries save to the mission server.
              </li>
            )}
          </ul>
        </Panel>
      </div>
    </PageShell>
  );
}
