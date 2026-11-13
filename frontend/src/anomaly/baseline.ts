import type { HealthMeasurement } from "../shared/types";

export interface Baseline {
  /** Personal typical level (median of clean history). */
  median: number;
  /** Robust spread estimate used for z-scores. */
  scale: number;
  /** Number of clean readings behind the baseline. */
  n: number;
}

const quantile = (sorted: number[], q: number): number => {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (pos - lo);
};

/**
 * Builds a personal baseline from a crew member's own history.
 * Uses the median + MAD (scaled to a normal sigma) so a few bad
 * readings can never skew the reference range.
 */
export function buildBaseline(
  series: HealthMeasurement[],
): Baseline | null {
  const vals = series
    .filter((m) => m.quality === "valid")
    .map((m) => m.value)
    .sort((a, b) => a - b);
  if (vals.length < 5) return null;

  const median = quantile(vals, 0.5);
  const mad = quantile(
    vals.map((v) => Math.abs(v - median)).sort((a, b) => a - b),
    0.5,
  );
  // Floor keeps flat series (e.g. constant sleep logs) from dividing by ~0.
  const floor = Math.max(0.02 * Math.abs(median), 1e-6);
  const scale = Math.max(1.4826 * mad, floor);
  return { median, scale, n: vals.length };
}
