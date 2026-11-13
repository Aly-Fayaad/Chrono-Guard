import type { FatigueStatus } from "../../shared/types";
import { MOOD, FATIGUE_SCORE } from "../shell/mood";

/**
 * Orbital fatigue gauge — a small echo of the Hub.
 * The planet sits at the center; the orbit arc fills with the status
 * color and the index + label always travel together (never color alone).
 */
export function EarthOrbitGauge({ status }: { status: FatigueStatus }) {
  const score = FATIGUE_SCORE[status];
  const mood = MOOD[status];
  const frac = score === null ? 0 : score / 100;
  const r = 40;
  const c = 2 * Math.PI * r;
  const dash = `${(frac * c * 0.75).toFixed(1)} ${c}`; // 270° max sweep

  return (
    <div
      role="img"
      aria-label={`Fatigue index ${score === null ? "not available" : `${score} of 100`}: ${mood.label}`}
      className="mx-auto w-full max-w-[220px]"
    >
      <svg viewBox="0 0 120 120" className="mx-auto block h-44 w-44">
        {/* static orbit track (270°, gap at bottom) */}
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="rgba(200,215,230,0.14)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${(c * 0.75).toFixed(1)} ${c}`}
          transform="rotate(135 60 60)"
        />
        {/* status arc */}
        {score !== null && (
          <circle
            cx="60"
            cy="60"
            r={r}
            fill="none"
            stroke={mood.accent}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={dash}
            transform="rotate(135 60 60)"
            style={{ filter: `drop-shadow(0 0 5px ${mood.accent}66)` }}
          />
        )}
        {/* small satellite marker at the arc tip */}
        {score !== null && frac > 0 && (
          <circle
            r="3.4"
            fill={mood.accent}
            transform={`rotate(${135 + frac * 270} 60 60) translate(0 ${-r})`}
          />
        )}
        {/* home planet */}
        <circle cx="60" cy="60" r="17" fill="#1c4d8f" />
        <circle cx="54" cy="54" r="7" fill="#3fae7c" opacity="0.8" />
        <circle cx="66" cy="64" r="5" fill="#3fae7c" opacity="0.6" />
        <circle cx="60" cy="60" r="17" fill="rgba(5,7,13,0.15)" />
        <text
          x="60"
          y="57"
          textAnchor="middle"
          fill="#E8EDF2"
          fontSize="15"
          fontFamily="IBM Plex Mono, monospace"
        >
          {score === null ? "—" : score}
        </text>
        <text x="60" y="70" textAnchor="middle" fill="#8A96A3" fontSize="6.5" letterSpacing="1.4">
          INDEX
        </text>
      </svg>
      <p className="mt-1 text-center text-[12px] font-medium" style={{ color: mood.accent }}>
        {mood.label}
      </p>
    </div>
  );
}
