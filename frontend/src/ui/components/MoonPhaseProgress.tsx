/**
 * Moon-phase progress for the check-in ritual: the Moon waxes from a thin
 * crescent to a full disc as the steps are completed. Text form is always
 * alongside ("Step 3 of 7 · Moon half full").
 */
export function MoonPhaseProgress({ step, total }: { step: number; total: number }) {
  const frac = Math.min(1, step / total);
  // Phase name follows the fraction of the ritual completed.
  const phase =
    frac === 0 ? "New Moon — beginning"
    : frac < 0.35 ? "Waxing crescent"
    : frac < 0.6 ? "First quarter"
    : frac < 0.9 ? "Waxing gibbous"
    : frac < 1 ? "Almost full"
    : "Full Moon — complete";

  return (
    <div className="glass-soft flex items-center gap-3 rounded-panel px-4 py-3" role="status" aria-label={`Check-in progress: step ${step} of ${total}, ${phase}`}>
      <svg width="44" height="44" viewBox="0 0 44 44" aria-hidden className="shrink-0">
        {/* orbit path */}
        <circle cx="22" cy="22" r="19" fill="none" stroke="rgba(201,210,220,0.18)" strokeWidth="1" strokeDasharray="1.5 3.5" />
        {/* dark disc */}
        <circle cx="22" cy="22" r="13" fill="#1a2230" stroke="rgba(201,210,220,0.25)" strokeWidth="1" />
        {/* lit fraction via mask: a circle shifted left/right creates a crescent→gibbous */}
        <defs>
          <clipPath id="moon-lit">
            <circle cx={22 - (1 - frac) * 2 * 13} cy="22" r="13" />
          </clipPath>
        </defs>
        <circle cx="22" cy="22" r="13" fill="#dfe8f2" opacity={Math.max(0.18, frac)} clipPath="url(#moon-lit)" />
        {/* full at completion */}
        {frac >= 1 && <circle cx="22" cy="22" r="13" fill="#dfe8f2" opacity="0.95" />}
        <circle cx="15" cy="18" r="2.4" fill="#8e99a6" opacity="0.35" />
        <circle cx="27" cy="27" r="3" fill="#8e99a6" opacity="0.3" />
      </svg>
      <div className="min-w-0 text-[12px]">
        <p className="tnum text-moonlight">Step {Math.min(step + 1, total)} of {total}</p>
        <p className="text-regolith">{phase}</p>
      </div>
      <div className="ml-auto hidden gap-1 sm:flex" aria-hidden>
        {Array.from({ length: total }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 w-4 rounded-full ${i < step ? "bg-silver/80" : "bg-hairline"}`}
          />
        ))}
      </div>
    </div>
  );
}
