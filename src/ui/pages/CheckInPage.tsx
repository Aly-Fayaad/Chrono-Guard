import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import type { HealthData } from "../hooks/useHealthData";
import { Panel } from "../components/Panel";
import { SectionHeader } from "../components/SectionHeader";

type Vitals = {
  heartRate: string;
  hrv: string;
  temperature: string;
  sleepHours: string;
};

const RANGE_HINTS: Record<keyof Vitals, string> = {
  heartRate: "30 – 220 bpm",
  hrv: "5 – 400 ms",
  temperature: "30 – 43 °C",
  sleepHours: "0 – 24 h",
};

const PLAUSIBLE: Record<keyof Vitals, [number, number]> = {
  heartRate: [30, 220],
  hrv: [5, 400],
  temperature: [30, 43],
  sleepHours: [0, 24],
};

const SLEEPINESS_LABELS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: "Exhausted",
  2: "Very tired",
  3: "Tired",
  4: "Slightly tired",
  5: "Alert",
};

const MOOD_LABELS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: "Very low",
  2: "Low",
  3: "Neutral",
  4: "Good",
  5: "Great",
};

const inputCls =
  "tnum motion-fade w-full rounded-panel border border-hairline bg-raised px-3 py-2 text-[13px] text-moonlight placeholder:text-ink focus:border-earth/60 focus:outline-none";

const fieldError = "mt-1 text-[11px] text-review";

function ScaleGroup({
  legend,
  labels,
  value,
  onChange,
}: {
  legend: string;
  labels: Record<1 | 2 | 3 | 4 | 5, string>;
  value: 1 | 2 | 3 | 4 | 5;
  onChange: (v: 1 | 2 | 3 | 4 | 5) => void;
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

export function CheckInPage({ health }: { health: HealthData }) {
  const [vitals, setVitals] = useState<Vitals>({ heartRate: "", hrv: "", temperature: "", sleepHours: "" });
  const [sleepiness, setSleepiness] = useState<1 | 2 | 3 | 4 | 5>(3);
  const [mood, setMood] = useState<1 | 2 | 3 | 4 | 5>(3);
  const [wokeAt, setWokeAt] = useState("");
  const [errors, setErrors] = useState<Partial<Record<keyof Vitals | "form", string>>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const set = (k: keyof Vitals) => (v: string) => {
    setVitals((prev) => ({ ...prev, [k]: v }));
    setErrors((prev) => ({ ...prev, [k]: undefined, form: undefined }));
    setSaved(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: typeof errors = {};
    const parsed: Record<keyof Vitals, number | undefined> = {
      heartRate: undefined, hrv: undefined, temperature: undefined, sleepHours: undefined,
    };
    (Object.keys(vitals) as (keyof Vitals)[]).forEach((k) => {
      const raw = vitals[k].trim();
      if (raw === "") return;
      const n = Number(raw);
      if (!Number.isFinite(n)) next[k] = "Enter a number.";
      else if (n < PLAUSIBLE[k][0] || n > PLAUSIBLE[k][1])
        next[k] = `Outside plausible range (${RANGE_HINTS[k]}). Save anyway? Re-check first.`;
      else parsed[k] = n;
    });
    if (!parsed.heartRate && !parsed.hrv && !parsed.temperature && !parsed.sleepHours) {
      next.form = "Add at least one vital-sign reading.";
    }
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;

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
      });
      setVitals({ heartRate: "", hrv: "", temperature: "", sleepHours: "" });
      setWokeAt("");
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <SectionHeader
        eyebrow="Deck A — Health"
        title="Health check-in"
        meta="Entries save locally and sync when connectivity returns."
      />

      <Panel label="Daily check-in" className="mx-auto max-w-xl">
        <form onSubmit={submit} noValidate className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {(
              [
                { k: "heartRate" as const, label: "Heart rate", unit: "bpm" },
                { k: "hrv" as const, label: "HRV (optional)", unit: "ms" },
                { k: "temperature" as const, label: "Temperature", unit: "°C" },
                { k: "sleepHours" as const, label: "Last sleep", unit: "h" },
              ]
            ).map((f) => (
              <div key={f.k}>
                <label htmlFor={`ck-${f.k}`} className="label-eyebrow">
                  {f.label} <span className="normal-case text-ink">({f.unit})</span>
                </label>
                <input
                  id={`ck-${f.k}`}
                  type="number"
                  inputMode="decimal"
                  step="any"
                  className={`mt-1.5 ${inputCls}`}
                  placeholder={RANGE_HINTS[f.k]}
                  value={vitals[f.k]}
                  onChange={(e) => set(f.k)(e.target.value)}
                  aria-invalid={Boolean(errors[f.k])}
                  aria-describedby={errors[f.k] ? `ck-${f.k}-err` : undefined}
                />
                {errors[f.k] && (
                  <p id={`ck-${f.k}-err`} className={fieldError} role="alert">
                    {errors[f.k]}
                  </p>
                )}
              </div>
            ))}
          </div>

          <ScaleGroup legend="Sleepiness (1–5)" labels={SLEEPINESS_LABELS} value={sleepiness} onChange={setSleepiness} />
          <ScaleGroup legend="Mood (1–5)" labels={MOOD_LABELS} value={mood} onChange={setMood} />

          <div>
            <label htmlFor="ck-wake" className="label-eyebrow">
              Last wake time <span className="normal-case text-ink">(optional)</span>
            </label>
            <input
              id="ck-wake"
              type="datetime-local"
              className={`mt-1.5 ${inputCls}`}
              value={wokeAt}
              onChange={(e) => {
                setWokeAt(e.target.value);
                setSaved(false);
              }}
            />
            <p className="mt-1 text-[11px] text-ink">Used to show hours awake on the mission schedule.</p>
          </div>

          {errors.form && (
            <p className={fieldError} role="alert">
              {errors.form}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-hairline pt-4">
            <button
              type="submit"
              disabled={saving}
              className="motion-fade inline-flex min-h-[44px] items-center rounded-panel border border-earth/50 bg-earth/10 px-4 text-[13px] font-medium text-earth hover:bg-earth/20 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save check-in"}
            </button>
            <button
              type="button"
              onClick={() => {
                setVitals({ heartRate: "", hrv: "", temperature: "", sleepHours: "" });
                setErrors({});
                setSaved(false);
              }}
              className="motion-fade inline-flex min-h-[44px] items-center rounded-panel border border-hairline px-3 text-[12px] text-regolith hover:text-moonlight"
            >
              Clear
            </button>
          </div>

          <p aria-live="polite" className="tnum flex items-center gap-2 text-[12px] text-nominal" role="status">
            {saved && (
              <>
                <CheckCircle2 size={14} aria-hidden />
                Saved locally, will sync when online.
              </>
            )}
          </p>
        </form>
      </Panel>
    </div>
  );
}
