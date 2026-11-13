import type { CSSProperties, ReactNode } from "react";

export type BodyKind = "earth" | "moon" | "sun" | "star" | "aurora" | "satellite";

/**
 * Procedural celestial body (pure SVG — works offline, no photo needed).
 * Rendered inside a focusable button by the Hub / MiniOrbitNav; here it is
 * just the artwork + optional label + one-line live teaser.
 */
export function CelestialBody({
  kind,
  size = 96,
  statusColor,
  rings = false,
  label,
  teaser,
  active = false,
  className = "",
  style,
}: {
  kind: BodyKind;
  /** diameter of the artwork in px */
  size?: number;
  /** optional status ring color (Earth atmosphere etc.) */
  statusColor?: string;
  /** show orbit rings around the body (Sun) */
  rings?: boolean;
  label?: ReactNode;
  teaser?: ReactNode;
  active?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  const art = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="block overflow-visible"
    >
      <defs>
        <radialGradient id={`g-${kind}`} cx="38%" cy="34%" r="75%">
          {kind === "earth" && (
            <>
              <stop offset="0%" stopColor="#8fd0ff" />
              <stop offset="45%" stopColor="#3f8fe8" />
              <stop offset="80%" stopColor="#1c4d8f" />
              <stop offset="100%" stopColor="#0e2a52" />
            </>
          )}
          {kind === "moon" && (
            <>
              <stop offset="0%" stopColor="#e6ebf1" />
              <stop offset="55%" stopColor="#aab4c0" />
              <stop offset="85%" stopColor="#77828f" />
              <stop offset="100%" stopColor="#4d5763" />
            </>
          )}
          {kind === "sun" && (
            <>
              <stop offset="0%" stopColor="#fff3d6" />
              <stop offset="50%" stopColor="#ffc25c" />
              <stop offset="100%" stopColor="#d97a1e" />
            </>
          )}
          {kind === "star" && (
            <>
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="60%" stopColor="#cfe0ff" />
              <stop offset="100%" stopColor="#7fa8e8" stopOpacity="0.2" />
            </>
          )}
          {kind === "satellite" && (
            <>
              <stop offset="0%" stopColor="#dfe8f2" />
              <stop offset="100%" stopColor="#8a96a3" />
            </>
          )}
          {kind === "aurora" && (
            <>
              <stop offset="0%" stopColor="#7de8c8" />
              <stop offset="55%" stopColor="#9b8cff" />
              <stop offset="100%" stopColor="#5a3f9e" />
            </>
          )}
        </radialGradient>
      </defs>

      {/* orbit rings (Sun — the 24h circadian cycle) */}
      {rings && (
        <g
          fill="none"
          stroke="rgba(255,194,92,0.35)"
          strokeWidth="0.7"
          strokeDasharray="2 3"
        >
          <circle cx="50" cy="50" r="42" />
          <circle cx="50" cy="50" r="47" strokeDasharray="1 5" stroke="rgba(200,215,230,0.25)" />
        </g>
      )}

      {/* soft halo */}
      {(kind === "star" || kind === "sun") && (
        <circle cx="50" cy="50" r={kind === "sun" ? 40 : 30} fill={kind === "sun" ? "rgba(255,194,92,0.16)" : "rgba(207,224,255,0.14)"} className="hub-glow" />
      )}

      {/* satellite body: small chassis + panels */}
      {kind === "satellite" ? (
        <g>
          <rect x="38" y="44" width="24" height="12" rx="2.5" fill="url(#g-satellite)" />
          <rect x="20" y="45.5" width="15" height="9" rx="1.5" fill="#4c9aff" opacity="0.75" />
          <rect x="65" y="45.5" width="15" height="9" rx="1.5" fill="#4c9aff" opacity="0.75" />
          <line x1="35" y1="50" x2="38" y2="50" stroke="#8a96a3" strokeWidth="1" />
          <line x1="62" y1="50" x2="65" y2="50" stroke="#8a96a3" strokeWidth="1" />
          <circle cx="50" cy="50" r="34" fill="none" stroke="rgba(201,210,220,0.22)" strokeWidth="0.7" strokeDasharray="1.5 4" />
        </g>
      ) : kind === "aurora" ? (
        <g>
          <ellipse cx="50" cy="56" rx="34" ry="16" fill="url(#g-aurora)" opacity="0.85" />
          <ellipse cx="50" cy="50" rx="26" ry="12" fill="#7de8c8" opacity="0.35" />
          <ellipse cx="44" cy="46" rx="14" ry="7" fill="#c8fff0" opacity="0.3" />
          <ellipse cx="58" cy="60" rx="18" ry="8" fill="#9b8cff" opacity="0.3" />
        </g>
      ) : kind === "star" ? (
        <g>
          <circle cx="50" cy="50" r="9" fill="url(#g-star)" />
          <path d="M50 30 L52.5 47.5 L70 50 L52.5 52.5 L50 70 L47.5 52.5 L30 50 L47.5 47.5 Z" fill="#eaf2ff" opacity="0.55" className="hub-glow" />
        </g>
      ) : (
        <g>
          {/* base sphere */}
          <circle cx="50" cy="50" r="30" fill={`url(#g-${kind})`} />
          {kind === "earth" && (
            <>
              {/* stylized landmasses (procedural, not to scale) */}
              <path
                d="M38 34 Q44 28 52 31 Q58 34 55 40 Q50 45 43 43 Q36 40 38 34 Z"
                fill="#3fae7c"
                opacity="0.85"
              />
              <path
                d="M55 48 Q63 46 66 52 Q68 58 62 61 Q55 62 53 57 Q52 51 55 48 Z"
                fill="#3fae7c"
                opacity="0.75"
              />
              <path
                d="M34 52 Q39 50 41 55 Q42 60 37 62 Q31 60 31 56 Q32 53 34 52 Z"
                fill="#35976b"
                opacity="0.7"
              />
              {/* cloud swirls */}
              <path d="M30 40 Q40 36 48 40" stroke="#ffffff" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.35" />
              <path d="M50 60 Q60 56 68 59" stroke="#ffffff" strokeWidth="1.4" strokeLinecap="round" fill="none" opacity="0.28" />
            </>
          )}
          {kind === "moon" && (
            <>
              <circle cx="41" cy="42" r="6" fill="#8e99a6" opacity="0.55" />
              <circle cx="56" cy="55" r="8" fill="#8e99a6" opacity="0.45" />
              <circle cx="47" cy="62" r="4" fill="#8e99a6" opacity="0.5" />
              <circle cx="60" cy="38" r="3.5" fill="#8e99a6" opacity="0.4" />
              <circle cx="38" cy="56" r="2.5" fill="#8e99a6" opacity="0.45" />
            </>
          )}
          {kind === "sun" && (
            <circle cx="50" cy="50" r="26" fill="#ffdf9e" opacity="0.35" className="hub-glow" />
          )}
          {/* terminator shading */}
          <path d="M50 20 a30 30 0 0 1 0 60 a34 34 0 0 0 0 -60" fill="rgba(5,7,13,0.25)" />
        </g>
      )}

      {/* status atmosphere ring — the ring carries the status color */}
      {statusColor && (
        <circle
          cx="50"
          cy="50"
          r={rings ? 36 : 36}
          fill="none"
          stroke={statusColor}
          strokeWidth="1.6"
          strokeOpacity="0.9"
          className="hub-glow"
          style={{ filter: `drop-shadow(0 0 6px ${statusColor})` }}
        />
      )}
    </svg>
  );

  return (
    <span className={`inline-flex flex-col items-center ${className}`} style={style}>
      {art}
      {label && (
        <span className="font-display mt-2 text-center text-[13px] font-medium text-moonlight">
          {label}
        </span>
      )}
      {teaser && (
        <span className="tnum mt-0.5 max-w-[220px] text-center text-[11px] leading-snug text-regolith">
          {teaser}
        </span>
      )}
      {active && <span aria-hidden className="sr-only">(current)</span>}
    </span>
  );
}
