/** Plain-language reasons list with mono tick markers. */
export function ReasonList({ reasons }: { reasons: string[] }) {
  return (
    <ul className="space-y-1.5">
      {reasons.map((r) => (
        <li key={r} className="flex gap-2 text-sm leading-relaxed text-moonlight/85">
          <span aria-hidden className="tnum shrink-0 text-regolith">
            ›
          </span>
          {r}
        </li>
      ))}
    </ul>
  );
}
