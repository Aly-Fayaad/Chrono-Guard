import type { ReactNode } from "react";

/** Page-level header: uppercase eyebrow, title, optional meta line. */
export function SectionHeader({
  eyebrow,
  title,
  meta,
  actions,
}: {
  eyebrow: string;
  title: string;
  meta?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="label-eyebrow">{eyebrow}</p>
        <h1 className="mt-0.5 text-[19px] font-medium text-moonlight">{title}</h1>
        {meta && <p className="tnum mt-0.5 text-[12px] text-regolith">{meta}</p>}
      </div>
      {actions}
    </div>
  );
}
