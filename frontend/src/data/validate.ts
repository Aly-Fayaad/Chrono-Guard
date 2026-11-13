import type { HealthMeasurement, MetricType } from "../shared/types";

/** Physiologically plausible bounds used to auto-flag bad entries. */
const PLAUSIBLE: Record<MetricType, [number, number]> = {
  heart_rate: [30, 220],
  hrv: [5, 400],
  temperature: [30, 43],
  sleep_hours: [0, 24],
};

/**
 * Validates an incoming measurement. Out-of-range values are marked invalid;
 * near-duplicates (entered within a minute of an existing one) are marked
 * suspect so anomaly detection can exclude them without losing the audit trail.
 */
export async function ingest(
  m: HealthMeasurement,
  existing: HealthMeasurement[],
): Promise<HealthMeasurement> {
  let quality = m.quality;
  const [lo, hi] = PLAUSIBLE[m.type];
  if (m.value < lo || m.value > hi) {
    quality = "invalid";
  } else if (
    existing.some(
      (e) => Math.abs(Date.parse(e.recordedAt) - Date.parse(m.recordedAt)) < 60_000,
    )
  ) {
    quality = "suspect";
  }
  return { ...m, quality };
}
