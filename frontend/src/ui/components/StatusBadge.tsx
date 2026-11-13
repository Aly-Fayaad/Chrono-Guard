import { CircleAlert, CircleCheck, CircleDashed, CircleMinus, Flag } from "lucide-react";
import type { DetectionStatus, FatigueStatus } from "../../shared/types";

export type BadgeVariant = "nominal" | "watch" | "review" | "insufficient" | "quality";

const CFG: Record<
  BadgeVariant,
  { icon: typeof CircleCheck; text: string; cls: string; hatch?: boolean }
> = {
  nominal: {
    icon: CircleCheck,
    text: "Nominal",
    cls: "border-nominal/35 text-nominal",
  },
  watch: {
    icon: CircleAlert,
    text: "Watch",
    cls: "border-watch/40 text-watch",
  },
  review: {
    icon: Flag,
    text: "Review suggested",
    cls: "border-review/45 text-review",
  },
  insufficient: {
    icon: CircleMinus,
    text: "Insufficient data",
    cls: "border-ink/40 text-ink",
    hatch: true,
  },
  quality: {
    icon: CircleDashed,
    text: "Data-quality warning",
    cls: "border-ink/40 text-ink",
    hatch: true,
  },
};

/** Detection status → badge variant (fixed, careful phrasing). */
export const DETECTION_BADGE: Record<DetectionStatus, { variant: BadgeVariant; label: string }> = {
  normal: { variant: "nominal", label: "Within personal range" },
  anomaly: { variant: "watch", label: "Unusual for baseline" },
  insufficient_baseline: { variant: "insufficient", label: "Not enough history" },
  data_quality: { variant: "quality", label: "Data-quality warning" },
};

/** Fatigue status → badge variant. */
export const FATIGUE_BADGE: Record<FatigueStatus, { variant: BadgeVariant; label: string }> = {
  insufficient_data: { variant: "insufficient", label: "Insufficient data" },
  no_flag: { variant: "nominal", label: "No fatigue flag" },
  monitor: { variant: "watch", label: "Monitor" },
  elevated_concern: { variant: "review", label: "Potential concern, review suggested" },
};

/**
 * Status chip. Always icon + LED + text label — never color alone.
 * Slate variants carry a diagonal hatch so quality/insufficient states
 * never read as a health alarm.
 */
export function StatusBadge({
  variant,
  label,
  className = "",
}: {
  variant: BadgeVariant;
  label: string;
  className?: string;
}) {
  const cfg = CFG[variant];
  const Icon = cfg.icon;
  return (
    <span
      className={`motion-fade inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium ${cfg.cls} ${
        cfg.hatch ? "hatch" : ""
      } ${className}`}
    >
      <span
        aria-hidden
        className="h-1.5 w-1.5 shrink-0 rounded-full ring-1 ring-current/30"
        style={{ backgroundColor: "currentColor" }}
      />
      <Icon size={12} aria-hidden className="shrink-0" />
      {label}
    </span>
  );
}
