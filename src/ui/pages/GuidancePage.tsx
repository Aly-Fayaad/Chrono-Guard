import { CheckCircle2, CircleCheck, CircleX, SquareCheck } from "lucide-react";
import type { FollowUpAction, GuidanceItem } from "../../shared/types";
import type { HealthData } from "../hooks/useHealthData";
import { Panel } from "../components/Panel";
import { SectionHeader } from "../components/SectionHeader";
import { EvidenceTag } from "../components/EvidenceTag";
import { EmptyState } from "../components/EmptyState";
import { METRICS } from "../config";

const ACTION_LABEL: Record<FollowUpAction, string> = {
  accepted: "Accepted",
  skipped: "Skipped",
  completed: "Completed",
};

const ACTION_STYLE: Record<FollowUpAction, string> = {
  accepted: "border-earth/45 text-earth",
  skipped: "border-ink/40 text-ink",
  completed: "border-nominal/40 text-nominal",
};

function GuidanceCard({
  item,
  action,
  onAction,
}: {
  item: GuidanceItem;
  action?: FollowUpAction;
  onAction: (a: FollowUpAction) => void;
}) {
  return (
    <Panel className={action === "completed" ? "opacity-80" : ""}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[14px] font-medium text-moonlight">{item.title}</h3>
          {item.metric && (
            <p className="tnum mt-0.5 text-[11px] text-regolith">
              Related metric: {METRICS[item.metric].label}
            </p>
          )}
        </div>
        <EvidenceTag evidence={item.evidence} />
      </div>

      <p className="mt-2 text-[13px] leading-relaxed text-regolith">{item.why}</p>

      {item.preconditions.length > 0 && (
        <div className="mt-3">
          <p className="label-eyebrow">Before you start</p>
          <ul className="mt-1.5 space-y-1">
            {item.preconditions.map((p) => (
              <li key={p} className="flex gap-2 text-[12px] text-moonlight/85">
                <span aria-hidden className="text-regolith">›</span>
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {item.warnings.length > 0 && (
        <div className="mt-3">
          {item.warnings.map((w) => (
            <p key={w} className="rounded border border-watch/35 bg-watch/5 p-2.5 text-[12px] leading-relaxed text-watch">
              <span className="font-medium">Note:</span> {w}
            </p>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-hairline pt-3.5">
        {!action && (
          <>
            <button
              onClick={() => onAction("accepted")}
              className="motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-panel border border-earth/50 bg-earth/10 px-3.5 text-[12px] font-medium text-earth hover:bg-earth/20"
            >
              <CircleCheck size={13} aria-hidden /> Accept
            </button>
            <button
              onClick={() => onAction("skipped")}
              className="motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-panel border border-hairline px-3.5 text-[12px] text-regolith hover:text-moonlight"
            >
              <CircleX size={13} aria-hidden /> Skip
            </button>
          </>
        )}
        {action === "accepted" && (
          <button
            onClick={() => onAction("completed")}
            className="motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-panel border border-nominal/50 bg-nominal/10 px-3.5 text-[12px] font-medium text-nominal hover:bg-nominal/20"
          >
            <SquareCheck size={13} aria-hidden /> Mark done
          </button>
        )}
        {action && (
          <span
            className={`tnum inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] ${ACTION_STYLE[action]}`}
            aria-label={`Status: ${ACTION_LABEL[action]}`}
          >
            {action === "completed" && <CheckCircle2 size={12} aria-hidden />}
            Status: {ACTION_LABEL[action]}
          </span>
        )}
      </div>
    </Panel>
  );
}

export function GuidancePage({ health }: { health: HealthData }) {
  const { data, guidanceActions, saveGuidanceAction, error } = health;

  return (
    <div className="space-y-4">
      <SectionHeader
        eyebrow="Deck A — Follow-up"
        title="Guidance"
        meta="Suggested actions generated from today's readings."
      />

      {error && <EmptyState title="Couldn't load guidance" hint={error} />}

      {!error && !data && <EmptyState title="Loading guidance…" />}

      {data &&
        (data.guidance.length === 0 ? (
          <EmptyState
            title="No actions needed. Keep logging your check-ins."
            hint="Guidance appears here when your readings move outside your personal baseline."
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {data.guidance.map((g) => (
              <GuidanceCard
                key={g.id}
                item={g}
                action={guidanceActions[g.id]}
                onAction={(a) => void saveGuidanceAction(g.id, a)}
              />
            ))}
          </div>
        ))}

      <p className="flex items-center gap-1.5 text-[11px] text-ink">
        Guidance summaries are informational. Review with a flight surgeon before
        changes to medical routines.
      </p>
    </div>
  );
}
