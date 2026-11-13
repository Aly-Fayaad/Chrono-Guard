import { CalendarRange, TriangleAlert } from "lucide-react";
import type { MissionTask } from "../../shared/types";
import { countdown, hoursBetween, metStamp } from "../lib/time";
import { useNow } from "../hooks/useNow";
import { Panel } from "./Panel";

/** Threshold (h) beyond which a demanding task gets a workload warning. */
const WAKE_WARNING_H = 14;

/**
 * Next mission task strip: title, live countdown, demand tag and a
 * workload-conflict warning when the crew member has been awake a long
 * time before a demanding task.
 */
export function TaskStrip({
  tasks,
  wake,
}: {
  tasks: MissionTask[];
  wake: string | null;
}) {
  const now = useNow(1000);
  const next = tasks
    .filter((t) => Date.parse(t.startsAt) > now.getTime())
    .sort((a, b) => a.startsAt.localeCompare(b.startsAt))[0];

  if (!next) {
    return (
      <Panel label="Next mission task">
        <div className="flex items-center gap-2.5 text-sm text-regolith">
          <CalendarRange size={15} aria-hidden className="text-ink" />
          No upcoming tasks scheduled.
        </div>
      </Panel>
    );
  }

  const awakeH = wake ? hoursBetween(wake, next.startsAt) : null;
  const conflict = next.demand === "demanding" && awakeH !== null && awakeH >= WAKE_WARNING_H;

  return (
    <Panel label="Next mission task">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[14px] font-medium text-moonlight">{next.title}</p>
        <span
          className={`rounded border px-2 py-0.5 font-mono text-[11px] ${
            next.demand === "demanding"
              ? "border-review/45 text-review"
              : "border-hairline text-regolith"
          }`}
        >
          {next.demand === "demanding" ? "DEMANDING" : "ROUTINE"}
        </span>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[12px]">
        <span className="tnum text-earth">{countdown(next.startsAt, now)}</span>
        <span className="text-regolith">{metStamp(next.startsAt)}</span>
      </div>
      {awakeH !== null && (
        <p className="tnum mt-2 text-[11px] text-regolith">
          Awake {awakeH} h at task start
        </p>
      )}
      {conflict && (
        <p
          role="status"
          className="mt-2.5 flex items-start gap-2 rounded border border-watch/40 bg-watch/5 p-2.5 text-[12px] leading-relaxed text-watch"
        >
          <TriangleAlert size={14} aria-hidden className="mt-0.5 shrink-0" />
          Long wake period before a demanding task — consider a rest block or moving the task earlier.
        </p>
      )}
    </Panel>
  );
}
