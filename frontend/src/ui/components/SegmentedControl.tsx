/** Segmented control (radio-like group of buttons with aria-pressed). */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = "md",
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel: string;
  size?: "sm" | "md";
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex overflow-hidden rounded-panel border border-hairline"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            aria-pressed={active}
            className={`motion-fade tnum min-h-[44px] px-3.5 text-[12px] ${
              size === "sm" ? "min-h-[36px] px-3" : ""
            } ${
              active
                ? "bg-raised text-earth"
                : "bg-panel text-regolith hover:bg-raised hover:text-moonlight"
            } ${active ? "" : "border-l border-hairline first:border-l-0"}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
