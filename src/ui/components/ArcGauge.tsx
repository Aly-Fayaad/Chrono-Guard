import type { FatigueStatus } from "../../shared/types";

/** Display score for the gauge, derived from the pipeline's assessment. */
const SCORE: Record<FatigueStatus, number | null> = {
  insufficient_data: null,
  no_flag: 18,
  monitor: 52,
  elevated_concern: 84,
};

const ARC_COLOR: Record<FatigueStatus, string> = {
  insufficient_data: "#6B7684",
  no_flag: "#3DD6B0",
  monitor: "#F2B84B",
  elevated_concern: "#F26B3A",
};

/**
 * Semicircular fatigue gauge. The value arc, the numeric score and the
 * status label carry the meaning together (not color alone).
 */
export function ArcGauge({ status, label }: { status: FatigueStatus; label: string }) {
  const score = SCORE[status];
  const color = ARC_COLOR[status];
  const r = 54;
  const cx = 70;
  const cy = 66;
  const sweep = Math.PI; // semicircle, left → right
  const frac = score === null ? 0 : score / 100;
  const end = {
    x: cx - r * Math.cos(frac * sweep),
    y: cy - r * Math.sin(frac * sweep),
  };
  const largeArc = 0;
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 ${largeArc} 1 ${cx + r} ${cy}`;

  return (
    <svg
      width={140}
      height={84}
      viewBox="0 0 140 84"
      role="img"
      aria-label={`${label}: ${score === null ? "not available" : `index ${score} of 100`}`}
      className="shrink-0"
    >
      <path d={arc} fill="none" stroke="rgba(200,215,230,0.14)" strokeWidth={8} strokeLinecap="round" />
      {score !== null && frac > 0 && (
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeLinecap="round"
        />
      )}
      <text
        x={cx}
        y={cy - 6}
        textAnchor="middle"
        fill="#E8EDF2"
        fontSize={22}
        fontFamily="IBM Plex Mono, monospace"
      >
        {score === null ? "—" : score}
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" fill="#8A96A3" fontSize={10} letterSpacing={2}>
        FATIGUE INDEX
      </text>
    </svg>
  );
}
