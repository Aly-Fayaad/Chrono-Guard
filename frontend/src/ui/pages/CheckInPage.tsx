import { useMemo, useState } from "react";
import { CheckCircle2, ChevronLeft, CircleCheck } from "lucide-react";
import { useHealth } from "../HealthContext";
import type { CheckInInput } from "../hooks/useHealthData";
import { PageShell } from "../shell/PageShell";
import { MoonPhaseProgress } from "../components/MoonPhaseProgress";

type Scale = 1 | 2 | 3 | 4 | 5;

const SLEEPINESS_LABELS: Record<Scale, string> = {
  1: "Exhausted", 2: "Very tired", 3: "Tired", 4: "Slightly tired", 5: "Alert",
};
const MOOD_LABELS: Record<Scale, string> = {
  1: "Very low", 2: "Low", 3: "Neutral", 4: "Good", 5: "Great",
};

const PLAUSIBLE: Record<string, [number, number]> = {
  heartRate: [30, 220],
  hrv: [5, 400],
  temperature: [30, 43],
  sleepHours: [0, 24],
};

const RANGE_HINTS: Record<string, string> = {
  heartRate: "30 – 220 bpm",
  hrv: "5 – 400 ms",
  temperature: "30 – 43 °C",
  sleepHours: "0 – 24 h",
};

const inputCls =
  "tnum motion-fade w-full rounded-panel border border-hairline bg-raised px-3 py-2 text-[15px] text-moonlight placeholder:text-ink focus:border-earth/60 focus:outline-none";

/**
 * Check-in as a ritual: one question per screen, moon-phase progress,
 * warm microcopy, no guilt language. Optional fields can be skipped.
 */
export function CheckInPage() {
  const health = useHealth();
  const [step, setStep] = useState(0);
  const [wokeAt, setWokeAt] = useState("");
  const [sleepHours, setSleepHours] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [hrv, setHrv] = useState("");
  const [temperature, setTemperature] = useState("");
  const [sleepiness, setSleepiness] = useState<Scale>(3);
  const [mood, setMood] = useState<Scale>(3);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const TOTAL = 7;
  const fieldError = "mt-1.5 text-[12px] text-watch";

  const steps = useMemo(
    () => [
      {
        phase: "Arrive",
        question: "Welcome back. When did you last wake?",
        body: (
          <div>
            <input
              id="ck-wake"
              type="datetime-local"
              aria-label="Last wake time (optional)"
              className={inputCls}
              value={wokeAt}
              onChange={(e) => setWokeAt(e.target.value)}
            />
            <p className="mt-1.5 text-[12px] text-ink">Optional — this helps the schedule track hours awake.</p>
          </div>
        ),
      },
      {
        phase: "Sleep",
        question: "How long did you sleep, in hours?",
        body: (
          <div>
            <input
              id="ck-sleep"
              type="number"
              inputMode="decimal"
              step="any"
              aria-label="Last sleep in hours (optional)"
              placeholder={RANGE_HINTS.sleepHours}
              className={inputCls}
              value={sleepHours}
              onChange={(e) => { setSleepHours(e.target.value); setError(null); }}
            />
            {error && <p className={fieldError} role="alert">{error}</p>}
          </div>
        ),
      },
      {
        phase: "Heart",
        question: "Your resting heart rate, in bpm?",
        body: (
          <div>
            <input
              id="ck-hr"
              type="number"
              inputMode="decimal"
              step="any"
              aria-label="Resting heart rate in bpm (optional)"
              placeholder={RANGE_HINTS.heartRate}
              className={inputCls}
              value={heartRate}
              onChange={(e) => { setHeartRate(e.target.value); setError(null); }}
            />
            {error && <p className={fieldError} role="alert">{error}</p>}
          </div>
        ),
      },
      {
        phase: "Heart",
        question: "HRV, if your device reports it?",
        body: (
          <div>
            <input
              id="ck-hrv"
              type="number"
              inputMode="decimal"
              step="any"
              aria-label="HRV in milliseconds (optional)"
              placeholder={RANGE_HINTS.hrv}
              className={inputCls}
              value={hrv}
              onChange={(e) => { setHrv(e.target.value); setError(null); }}
            />
            <p className="mt-1.5 text-[12px] text-ink">Fine to skip — the ritual works without it.</p>
            {error && <p className={fieldError} role="alert">{error}</p>}
          </div>
        ),
      },
      {
        phase: "Warmth",
        question: "Your temperature, in °C?",
        body: (
          <div>
            <input
              id="ck-temp"
              type="number"
              inputMode="decimal"
              step="any"
              aria-label="Temperature in degrees Celsius (optional)"
              placeholder={RANGE_HINTS.temperature}
              className={inputCls}
              value={temperature}
              onChange={(e) => { setTemperature(e.target.value); setError(null); }}
            />
            {error && <p className={fieldError} role="alert">{error}</p>}
          </div>
        ),
      },
      {
        phase: "Sleepiness",
        question: "How sleepy do you feel right now?",
        body: (
          <ScaleGroup
            legend="Sleepiness (1–5)"
            labels={SLEEPINESS_LABELS}
            value={sleepiness}
            onChange={setSleepiness}
          />
        ),
      },
      {
        phase: "Mood",
        question: "And how is your mood today?",
        body: (
          <ScaleGroup
            legend="Mood (1–5)"
            labels={MOOD_LABELS}
            value={mood}
            onChange={setMood}
          />
        ),
      },
    ],
    [wokeAt, sleepHours, heartRate, hrv, temperature, sleepiness, mood, error],
  );

  const current = steps[step];

  async function finish() {
    const parsed: Record<string, number | undefined> = {};
    const check = (k: string, raw: string) => {
      const v = raw.trim();
      if (v === "") return;
      const n = Number(v);
      if (!Number.isFinite(n) || n < PLAUSIBLE[k][0] || n > PLAUSIBLE[k][1]) {
        setError(`That value looks out of range (${RANGE_HINTS[k]}). You can skip this one if you prefer.`);
        return true;
      }
      parsed[k] = n;
      return false;
    };
    setError(null);
    if (check("sleepHours", sleepHours) || check("heartRate", heartRate) || check("hrv", hrv) || check("temperature", temperature)) return;
    if (
      parsed.sleepHours === undefined && parsed.heartRate === undefined &&
      parsed.hrv === undefined && parsed.temperature === undefined
    ) {
      setError("Add at least one vital reading so the console has something to learn from.");
      return;
    }

    setSaving(true);
    try {
      await health.saveCheckIn({
        heartRate: parsed.heartRate,
        hrv: parsed.hrv,
        temperature: parsed.temperature,
        sleepHours: parsed.sleepHours,
        sleepiness,
        mood,
        wokeAt: wokeAt || undefined,
      } satisfies CheckInInput);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  function next() {
    if (step < TOTAL - 1) setStep(step + 1);
    else void finish();
  }

  return (
    <PageShell title="Check-in" crumb="Moon" bodyName="Moon">
      <div className="mx-auto max-w-xl space-y-4">
        <div>
          <p className="label-eyebrow">Moon · A quiet daily ritual</p>
          <h1 className="font-display mt-0.5 text-[22px] font-medium text-moonlight">Check-in</h1>
          <p className="mt-1 text-[12px] text-regolith">
            Seven small moments with yourself. Entries save locally and sync when connectivity returns.
          </p>
        </div>

        <MoonPhaseProgress step={saved ? TOTAL : step} total={TOTAL} />

        {saved ? (
          <div className="glass rounded-panel p-8 text-center" role="status" aria-live="polite">
            <CheckCircle2 size={36} aria-hidden className="mx-auto text-nominal" />
            <h2 className="font-display mt-3 text-[17px] text-moonlight">Logged. Gently done.</h2>
            <p className="mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-regolith">
              Your readings are stored and will travel to the medical team when the relay is
              available. The Moon waxes a little with every check-in — thank you for keeping
              the rhythm.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <a
                href="#/restore"
                className="motion-fade inline-flex min-h-[44px] items-center rounded-panel border border-aurora/50 bg-aurora/10 px-4 text-[13px] text-aurora hover:bg-aurora/20"
              >
                Take a slow breath in the Aurora
              </a>
              <button
                onClick={() => {
                  setSaved(false);
                  setStep(0);
                  setSleepHours(""); setHeartRate(""); setHrv(""); setTemperature(""); setWokeAt("");
                }}
                className="motion-fade inline-flex min-h-[44px] items-center rounded-panel border border-hairline px-4 text-[12px] text-regolith hover:text-moonlight"
              >
                Start another
              </button>
            </div>
          </div>
        ) : (
          <div className="glass rounded-panel p-6 sm:p-8" aria-live="polite">
            <p className="label-eyebrow">
              Step {step + 1} of {TOTAL} · {current.phase}
            </p>
            <h2 className="font-display mt-2 text-[18px] leading-snug text-moonlight">{current.question}</h2>
            <div className="mt-5">{current.body}</div>
            {error && (
              <p className={fieldError} role="alert">
                {error}
              </p>
            )}

            <div className="mt-7 flex items-center justify-between gap-3 border-t border-hairline pt-4">
              <button
                type="button"
                onClick={() => setStep(Math.max(0, step - 1))}
                disabled={step === 0}
                className="motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-panel border border-hairline px-3.5 text-[12px] text-regolith hover:text-moonlight disabled:opacity-30"
              >
                <ChevronLeft size={14} aria-hidden /> Back
              </button>
              <button
                type="button"
                onClick={next}
                disabled={saving}
                className="motion-fade inline-flex min-h-[44px] items-center rounded-panel border border-earth/50 bg-earth/10 px-5 text-[13px] font-medium text-earth hover:bg-earth/20 disabled:opacity-50"
              >
                {saving ? "Saving…" : step === TOTAL - 1 ? "Complete check-in" : "Continue"}
              </button>
            </div>
          </div>
        )}

        <p className="flex items-center gap-1.5 text-[11px] text-ink">
          <CircleCheck size={12} aria-hidden />
          Skipping optional steps is always okay. Nothing here is a diagnosis.
        </p>
      </div>
    </PageShell>
  );
}

function ScaleGroup({
  legend,
  labels,
  value,
  onChange,
}: {
  legend: string;
  labels: Record<Scale, string>;
  value: Scale;
  onChange: (v: Scale) => void;
}) {
  return (
    <fieldset>
      <legend className="label-eyebrow mb-2">{legend}</legend>
      <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label={legend}>
        {([1, 2, 3, 4, 5] as const).map((n) => {
          const active = value === n;
          return (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(n)}
              className={`motion-fade flex min-h-[56px] flex-col items-center justify-center gap-0.5 rounded-panel border px-1 ${
                active
                  ? "border-earth/70 bg-raised text-moonlight"
                  : "border-hairline bg-panel text-regolith hover:border-regolith/40"
              }`}
            >
              <span className="tnum text-[15px]">{n}</span>
              <span className="text-[9px] leading-tight">{labels[n]}</span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
