import { Sparkline } from "./Sparkline";
import { StatusBadge, type BadgeVariant } from "./StatusBadge";

/**
 * Metric tile: eyebrow label, big mono value + unit, sparkline and a
 * StatusBadge. Selectable — acts as the chart metric chooser on Today.
 */
export function MetricTile({
  label,
  unit,
  value,
  spark,
  statusVariant,
  statusLabel,
  selected,
  onSelect,
  hatched,
  ariaLabel,
}: {
  label: string;
  unit: string;
  value: number | null;
  spark: number[];
  statusVariant: BadgeVariant;
  statusLabel: string;
  selected: boolean;
  onSelect: () => void;
  hatched?: boolean;
  ariaLabel: string;
}) {
  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={ariaLabel}
      className={`motion-fade relative min-h-[44px] rounded-panel border p-4 text-left ${
        selected
          ? "border-earth/70 bg-raised"
          : "border-hairline bg-panel hover:border-regolith/40"
      }`}
    >
      {hatched && <span aria-hidden className="hatch pointer-events-none absolute inset-0 rounded-panel" />}
      <p className="label-eyebrow">{label}</p>
      <p className="tnum mt-1.5 text-[26px] leading-none text-moonlight">
        {value ?? "n/a"}
        <span className="ml-1 text-[12px] text-regolith">{unit}</span>
      </p>
      <div className="mt-2.5">
        <Sparkline values={spark} color={statusVariant === "nominal" ? "#3DD6B0" : statusVariant === "watch" ? "#F2B84B" : "#6B7684"} label={`${label} sparkline`} className="h-7 w-full" />
      </div>
      <div className="mt-2">
        <StatusBadge variant={statusVariant} label={statusLabel} />
      </div>
      {selected && <span aria-hidden className="absolute inset-x-4 top-0 h-0.5 bg-earth" />}
    </button>
  );
}
