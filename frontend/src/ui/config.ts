import type { MetricType } from "../shared/types";

/** Identifier of the signed-in crew member (single-crew demo build). */
export const CREW_ID = "crew-demo-01";

/** Mission epoch used by the MET clock and D+ labels. */
export const MISSION_START = new Date("2026-10-30T07:00:00Z");

/** Display metadata for the four tracked vitals. */
export const METRICS: Record<MetricType, { label: string; unit: string }> = {
  heart_rate: { label: "Heart rate", unit: "bpm" },
  hrv: { label: "HRV", unit: "ms" },
  temperature: { label: "Temperature", unit: "°C" },
  sleep_hours: { label: "Sleep", unit: "h" },
};

export const METRIC_ORDER: MetricType[] = [
  "heart_rate",
  "hrv",
  "temperature",
  "sleep_hours",
];
