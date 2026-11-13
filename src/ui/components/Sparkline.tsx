/** Compact SVG sparkline (no chart lib) for metric tiles and trend view. */
export function Sparkline({
  values,
  color,
  highlightWindow = 0,
  label,
  className = "h-8 w-full",
}: {
  values: number[];
  color: string;
  /** Shade the trailing N-point window (sustained-change highlight). */
  highlightWindow?: number;
  label: string;
  className?: string;
}) {
  const w = 100;
  const h = 32;
  const pad = 3;
  if (values.length < 2) {
    return (
      <svg className={className} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label}>
        <line x1={pad} y1={h / 2} x2={w - pad} y2={h / 2} stroke={color} strokeOpacity={0.4} strokeDasharray="2 3" />
      </svg>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => pad + (i * (w - pad * 2)) / (values.length - 1);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const hlStart = values.length - highlightWindow;
  return (
    <svg className={className} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label}>
      {highlightWindow > 0 && hlStart >= 0 && (
        <rect
          x={x(hlStart) - 2}
          y={0}
          width={w - x(hlStart) + 2}
          height={h}
          fill="rgba(242,107,58,0.10)"
        />
      )}
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(values.length - 1)} cy={y(values[values.length - 1]!)} r={2} fill={color} />
    </svg>
  );
}
