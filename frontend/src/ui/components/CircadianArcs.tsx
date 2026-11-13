import { metStamp, earthClockHour } from "../lib/time";

const CX = 150;
const CY = 120;
const R = 96;

/** hour (0–24) → point on the semicircle (hour 0 = left, hour 12 = top). */
function pt(h: number, r = R): string {
  const a = (Math.PI * (180 - (h / 24) * 180)) / 180;
  return `${(CX + r * Math.cos(a)).toFixed(1)} ${(CY - r * Math.sin(a)).toFixed(1)}`;
}

/** filled wedge for an hour span, closed to the baseline center. */
function wedge(h1: number, h2: number): string {
  return `M ${CX} ${CY} L ${pt(h1)} A ${R} ${R} 0 0 1 ${pt(h2)} Z`;
}

/** stroked arc for an hour span. */
function arcSeg(h1: number, h2: number): string {
  return `M ${pt(h1)} A ${R} ${R} 0 0 1 ${pt(h2)}`;
}

const LIGHT = [6.5, 21.5] as const; // 06:30 → 21:30 station bright-light window

/**
 * Circadian light guidance: recommended bright-light and dark/sleep
 * windows as sun/shadow arcs over the published 24-hour Earth clock
 * (06:30–21:30 light, 21:30–06:30 dark). A marker shows "now"; a dashed
 * marker shows the last wake time when known. The text line is the
 * accessible summary.
 */
export function CircadianArcs({ now, wake }: { now: Date; wake: string | null }) {
  const localH = earthClockHour(now);
  const wakeH = wake ? earthClockHour(wake) : null;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg
        viewBox="0 0 300 140"
        className="h-40 w-full max-w-md"
        role="img"
        aria-label={`Circadian light guidance. Bright light recommended from 06:30 to 21:30, dark and sleep from 21:30 to 06:30. Now is ${metStamp(now)}.`}
      >
        {/* baseline */}
        <line x1="30" y1={CY} x2="270" y2={CY} stroke="rgba(200,215,230,0.2)" strokeWidth="1" />

        {/* dark/sleep window: 21:30→24:00 and 00:00→06:30 (shadow wedges) */}
        <path d={wedge(LIGHT[1], 24)} fill="rgba(201,210,220,0.10)" />
        <path d={wedge(0, LIGHT[0])} fill="rgba(201,210,220,0.10)" />
        <path d={arcSeg(LIGHT[1], 24)} fill="none" stroke="rgba(201,210,220,0.5)" strokeWidth="2" strokeDasharray="3 4" />
        <path d={arcSeg(0, LIGHT[0])} fill="none" stroke="rgba(201,210,220,0.5)" strokeWidth="2" strokeDasharray="3 4" />

        {/* bright-light window (amber wedge + solid arc) */}
        <path d={wedge(LIGHT[0], LIGHT[1])} fill="rgba(255,194,92,0.16)" />
        <path d={arcSeg(LIGHT[0], LIGHT[1])} fill="none" stroke="#ffc25c" strokeWidth="2" strokeOpacity="0.85" />

        {/* hour ticks */}
        {[0, 6, 12, 18, 24].map((h) => {
          const a = (Math.PI * (180 - (h / 24) * 180)) / 180;
          return (
            <g key={h}>
              <line
                x1={CX + R * Math.cos(a)}
                y1={CY - R * Math.sin(a)}
                x2={CX + (R + 8) * Math.cos(a)}
                y2={CY - (R + 8) * Math.sin(a)}
                stroke="rgba(200,215,230,0.3)"
                strokeWidth="1"
              />
              <text
                x={CX + (R + 18) * Math.cos(a)}
                y={CY - (R + 14) * Math.sin(a) + 3}
                textAnchor="middle"
                fontSize="9"
                fill="#8A96A3"
                fontFamily="IBM Plex Mono, monospace"
              >
                {String(h).padStart(2, "0")}:00
              </text>
            </g>
          );
        })}

        {/* sun glyph in the light window, moon glyph in the dark window */}
        <circle cx={CX + 74 * Math.cos((Math.PI * 112.5) / 180)} cy={CY - 74 * Math.sin((Math.PI * 112.5) / 180)} r="6" fill="#ffc25c" opacity="0.9" />
        <circle cx={CX + 74 * Math.cos((Math.PI * 165) / 180)} cy={CY - 74 * Math.sin((Math.PI * 165) / 180)} r="5" fill="#aab4c0" opacity="0.7" />

        {/* now marker */}
        <line
          x1={CX}
          y1={CY}
          x2={CX + (R + 8) * Math.cos((Math.PI * (180 - (localH / 24) * 180)) / 180)}
          y2={CY - (R + 8) * Math.sin((Math.PI * (180 - (localH / 24) * 180)) / 180)}
          stroke="#4c9aff"
          strokeWidth="1.6"
        />
        <circle
          cx={CX + (R + 8) * Math.cos((Math.PI * (180 - (localH / 24) * 180)) / 180)}
          cy={CY - (R + 8) * Math.sin((Math.PI * (180 - (localH / 24) * 180)) / 180)}
          r="3.2"
          fill="#4c9aff"
        />
        <text
          x={CX + (R + 22) * Math.cos((Math.PI * (180 - (localH / 24) * 180)) / 180)}
          y={CY - (R + 22) * Math.sin((Math.PI * (180 - (localH / 24) * 180)) / 180) + 3}
          textAnchor="middle"
          fontSize="9"
          fill="#4C9AFF"
          fontFamily="IBM Plex Mono, monospace"
        >
          now
        </text>

        {/* last wake marker */}
        {wakeH !== null && (
          <line
            x1={CX}
            y1={CY}
            x2={CX + R * Math.cos((Math.PI * (180 - (wakeH / 24) * 180)) / 180)}
            y2={CY - R * Math.sin((Math.PI * (180 - (wakeH / 24) * 180)) / 180)}
            stroke="#3dd6b0"
            strokeWidth="1.2"
            strokeDasharray="3 3"
            opacity="0.8"
          />
        )}
      </svg>
      <p className="text-center text-[11px] text-ink">
        Blue line: now. Green dashed: last wake. Amber: bright-light window. Silver: dark/sleep window.
      </p>
    </div>
  );
}
