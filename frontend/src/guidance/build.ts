import type {
  DetectionResult,
  GuidanceItem,
  MetricType,
} from "../shared/types";

let guidanceSeq = 0;
const item = (g: Omit<GuidanceItem, "id">): GuidanceItem => ({
  id: `g-${++guidanceSeq}`,
  ...g,
});

/**
 * Presentation-only guidance derived from the backend's detections.
 * The detections themselves are computed by the API; this only turns them
 * into the existing card copy and never asserts a diagnosis.
 */
export function buildGuidance(detections: DetectionResult[]): GuidanceItem[] {
  const byMetric = new Map(detections.map((d) => [d.metric, d]));
  const flagged = (t: MetricType) => byMetric.get(t)?.status === "anomaly";
  const items: GuidanceItem[] = [];

  if (flagged("heart_rate") || flagged("hrv")) {
    items.push(
      item({
        title: "Take a 15-minute low-stimulation rest before your next task",
        why: "Heart-rate/HRV readings are unusual for your baseline; a quiet rest often settles autonomic load.",
        evidence: "limited",
        preconditions: [
          "Confirm the wearable is seated correctly and re-measure once",
        ],
        warnings: [
          "Chest pain, palpitations or breathlessness → contact the flight surgeon immediately",
        ],
        metric: flagged("heart_rate") ? "heart_rate" : "hrv",
      }),
    );
  }

  if (flagged("sleep_hours")) {
    items.push(
      item({
        title: "Anchor tonight's sleep window to the station light cycle",
        why: "Sleep duration drifted from your personal range; light-aligned sleep windows support faster re-entrainment.",
        evidence: "well_supported",
        preconditions: ["Dim the panels 45 minutes before the window"],
        warnings: ["Caffeine within 6 h of the window will blunt the effect"],
        metric: "sleep_hours",
      }),
    );
  }

  if (flagged("temperature")) {
    items.push(
      item({
        title: "Log a follow-up temperature in 30 minutes",
        why: "Core-temperature estimates can spike after exercise or suit work; a quiet re-check distinguishes them.",
        evidence: "well_supported",
        preconditions: ["Rest quietly for 10 minutes first"],
        warnings: [],
        metric: "temperature",
      }),
    );
  }

  items.push(
    item({
      title: "Keep the daily check-in at the same station time",
      why: "Regular timing sharpens your personal baseline, so future anomalies are detected earlier.",
      evidence: "well_supported",
      preconditions: [],
      warnings: [],
    }),
  );
  items.push(
    item({
      title: "Request a human review of today's readings",
      why: "Flagged patterns benefit from a flight-surgeon look before mission-critical days.",
      evidence: "needs_review",
      preconditions: ["Export the current report from the Today dashboard"],
      warnings: [],
    }),
  );

  return items;
}
