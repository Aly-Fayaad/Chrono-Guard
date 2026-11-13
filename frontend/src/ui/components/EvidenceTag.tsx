import { BadgeCheck, CircleAlert, Info } from "lucide-react";
import type { GuidanceEvidence } from "../../shared/types";

const CFG: Record<
  GuidanceEvidence,
  { icon: typeof Info; label: string; cls: string }
> = {
  well_supported: { icon: BadgeCheck, label: "Well supported", cls: "border-nominal/35 text-nominal" },
  limited: { icon: Info, label: "Limited evidence", cls: "border-watch/40 text-watch" },
  needs_review: { icon: CircleAlert, label: "Needs human review", cls: "border-review/45 text-review" },
};

/** Evidence-strength chip on guidance cards. */
export function EvidenceTag({ evidence }: { evidence: GuidanceEvidence }) {
  const cfg = CFG[evidence];
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] ${cfg.cls}`}
      title={`Evidence: ${cfg.label.toLowerCase()}`}
    >
      <Icon size={12} aria-hidden />
      {cfg.label}
    </span>
  );
}
