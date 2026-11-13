import type { ReactNode } from "react";

/** One L-shaped HUD corner tick (8px). */
function Corner({ position }: { position: "tl" | "tr" | "bl" | "br" }) {
  const pos = {
    tl: "-top-px -left-px border-t border-l",
    tr: "-top-px -right-px border-t border-r",
    bl: "-bottom-px -left-px border-b border-l",
    br: "-bottom-px -right-px border-b border-r",
  }[position];
  return (
    <span
      aria-hidden
      className={`pointer-events-none absolute h-2 w-2 border-earth/45 ${pos}`}
    />
  );
}

/**
 * Console panel: flat fill, hairline border, 8px radius, HUD corner ticks.
 * Optional uppercase eyebrow header and right-aligned actions.
 */
export function Panel({
  label,
  actions,
  children,
  className = "",
  bodyClassName = "p-4 sm:p-5",
}: {
  label?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`glass relative rounded-panel ${className}`}>
      <Corner position="tl" />
      <Corner position="tr" />
      <Corner position="bl" />
      <Corner position="br" />
      {(label || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-4 py-2.5 sm:px-5">
          {label ? <h2 className="label-eyebrow">{label}</h2> : <span aria-hidden />}
          {actions}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}
