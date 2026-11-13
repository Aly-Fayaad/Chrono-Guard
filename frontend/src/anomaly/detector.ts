import type {
  DetectionResult,
  HealthMeasurement,
  MetricType,
} from "../shared/types";
import { buildBaseline } from "./baseline";

export const DEFAULT_CONFIG = {
  zThreshold: 3.5,
  trendWindow: 3,
  minBaseline: 5,
} as const;

export interface DetectorConfig {
  zThreshold: number;
  trendWindow: number;
  minBaseline: number;
}

/**
 * Compares the most recent readings against the crew member's own
 * baseline and classifies the result:
 * - sudden:    latest reading is far from baseline after a stable stretch
 * - sustained: every reading in the trend window is far from baseline
 * - data_quality: recent readings failed quality checks
 * - insufficient_baseline: not enough clean history yet
 */
export function detect(
  series: HealthMeasurement[],
  config: DetectorConfig = DEFAULT_CONFIG,
): DetectionResult {
  const metric: MetricType = series[0]?.type ?? "heart_rate";

  if (series.length < config.minBaseline + 1) {
    return {
      metric,
      status: "insufficient_baseline",
      reason: `At least ${config.minBaseline} valid readings are needed before today's value can be compared to your personal baseline.`,
    };
  }

  const recent = series.slice(-config.trendWindow);
  const baseline = buildBaseline(series.slice(0, series.length - config.trendWindow));

  if (!baseline) {
    return {
      metric,
      status: "insufficient_baseline",
      reason: "Not enough clean history to build a personal baseline yet.",
    };
  }

  if (recent.some((m) => m.quality !== "valid")) {
    return {
      metric,
      status: "data_quality",
      reason:
        "One or more recent readings were flagged by quality checks — re-measure before trusting the trend.",
    };
  }

  const zScores = recent.map((m) => (m.value - baseline.median) / baseline.scale);
  const lastZ = zScores[zScores.length - 1]!;
  const flagged = zScores.filter((z) => Math.abs(z) >= config.zThreshold).length;

  if (flagged === zScores.length) {
    return {
      metric,
      status: "anomaly",
      zScore: lastZ,
      event: {
        kind: "sustained",
        explanation: `All of the last ${config.trendWindow} readings sit ${Math.abs(lastZ).toFixed(1)}σ from your usual ${baseline.median.toFixed(1)} level.`,
      },
    };
  }

  if (Math.abs(lastZ) >= config.zThreshold) {
    return {
      metric,
      status: "anomaly",
      zScore: lastZ,
      event: {
        kind: "sudden",
        explanation: `Today's reading jumps ${Math.abs(lastZ).toFixed(1)}σ away from your usual ${baseline.median.toFixed(1)} level after a stable stretch.`,
      },
    };
  }

  return { metric, status: "normal", zScore: lastZ };
}
