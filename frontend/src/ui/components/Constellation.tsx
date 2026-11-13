/**
 * Constellation diagram for Guidance: one star per suggestion, connected
 * by soft lines. Hovering/focusing a card brightens the matching star.
 * Stars pulse very gently (static when reduce-effects is on).
 */
export function Constellation({
  count,
  highlight,
  resolved,
}: {
  count: number;
  highlight: number | null;
  resolved: boolean[];
}) {
  // Deterministic star placement along a gentle arc, left → right.
  const n = Math.max(count, 1);
  const pts = Array.from({ length: n }).map((_, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const x = 40 + t * 320;
    const y = 62 - Math.sin(t * Math.PI) * 30 + Math.cos(t * 4.2) * 8;
    return { x, y, i };
  });

  return (
    <svg
      viewBox="0 0 400 100"
      className="h-28 w-full"
      role="img"
      aria-label={`Constellation of ${n} suggestion${n > 1 ? "s" : ""}. Stars light up as you follow them.`}
    >
      {/* connecting lines */}
      {pts.slice(0, -1).map((p, i) => (
        <line
          key={`l-${i}`}
          x1={p.x}
          y1={p.y}
          x2={pts[i + 1].x}
          y2={pts[i + 1].y}
          stroke={highlight === i || highlight === i + 1 ? "rgba(155,140,255,0.65)" : "rgba(155,140,255,0.2)"}
          strokeWidth={highlight === i || highlight === i + 1 ? 1.4 : 0.8}
          strokeDasharray="2 4"
        />
      ))}
      {/* stars */}
      {pts.map((p) => {
        const active = highlight === p.i;
        const done = resolved[p.i];
        const color = done ? "#3dd6b0" : active ? "#e8edf2" : "#9b8cff";
        return (
          <g key={p.i} transform={`translate(${p.x} ${p.y})`}>
            {active && <circle r="9" fill={color} opacity="0.2" />}
            <path
              d="M0 -7 L1.8 -1.8 L7 0 L1.8 1.8 L0 7 L-1.8 1.8 L-7 0 L-1.8 -1.8 Z"
              fill={color}
              opacity={active ? 1 : 0.75}
              className={active ? "hub-glow" : undefined}
            />
            <circle r="1.4" fill={color} />
          </g>
        );
      })}
      {/* horizon hint */}
      <line x1="20" y1="88" x2="380" y2="88" stroke="rgba(200,215,230,0.14)" strokeWidth="1" />
    </svg>
  );
}
