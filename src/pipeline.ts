import { db } from "./data/db";
import { detect } from "./anomaly/detector";
import type {
  CheckIn,
  DetectionResult,
  FatigueAssessment,
  GuidanceItem,
  HealthMeasurement,
  MetricType,
  PipelineResult,
} from "./shared/types";

export type { PipelineResult };

export const METRIC_TYPES: MetricType[] = [
  "heart_rate",
  "hrv",
  "temperature",
  "sleep_hours",
];

/**
 * Reads everything stored locally for a crew member and produces the
 * daily picture: per-metric series, anomaly detections, a fatigue
 * assessment, and guidance items.
 */
export async function runPipeline(crewId: string): Promise<PipelineResult> {
  const [allMeasurements, tasks, checkins] = await Promise.all([
    db.measurements.where("crewId").equals(crewId).toArray(),
    db.tasks.where("crewId").equals(crewId).toArray(),
    db.checkins.where("crewId").equals(crewId).toArray(),
  ]);

  const series: Record<MetricType, HealthMeasurement[]> = {
    heart_rate: [],
    hrv: [],
    temperature: [],
    sleep_hours: [],
  };
  for (const m of allMeasurements) series[m.type].push(m);
  for (const type of METRIC_TYPES) {
    series[type].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
  }

  const detections = METRIC_TYPES.map((type) => detect(series[type]));
  const assessment = assessFatigue(series, checkins, detections);
  const guidance = buildGuidance(detections);

  tasks.sort((a, b) => a.startsAt.localeCompare(b.startsAt));
  return { series, detections, assessment, guidance, tasks };
}

function assessFatigue(
  series: Record<MetricType, HealthMeasurement[]>,
  checkins: CheckIn[],
  detections: DetectionResult[],
): FatigueAssessment {
  const recentCheckins = [...checkins]
    .sort((a, b) => b.recordedAt.localeCompare(a.recordedAt))
    .slice(0, 3);
  const recentSleep = series.sleep_hours
    .slice(-3)
    .filter((m) => m.quality === "valid");
  const anomalyCount = detections.filter((d) => d.status === "anomaly").length;

  if (!recentCheckins.length || recentSleep.length < 2) {
    return {
      status: "insufficient_data",
      reasons: [
        "Log a few check-ins and sleep entries so the companion can learn your personal rhythm.",
      ],
    };
  }

  const reasons: string[] = [];
  const avgSleepiness =
    recentCheckins.reduce((s, c) => s + c.sleepiness, 0) / recentCheckins.length;
  const avgSleep =
    recentSleep.reduce((s, m) => s + m.value, 0) / recentSleep.length;
  reasons.push(
    `Sleepiness averaged ${avgSleepiness.toFixed(1)}/5 over the last ${recentCheckins.length} check-ins.`,
  );
  reasons.push(
    `Sleep averaged ${avgSleep.toFixed(1)} h per night over the last ${recentSleep.length} nights.`,
  );
  if (anomalyCount > 0) {
    reasons.push(
      `${anomalyCount} metric${anomalyCount > 1 ? "s" : ""} moved outside your personal baseline.`,
    );
  }

  if (avgSleepiness >= 4 && (avgSleep < 6 || anomalyCount >= 2)) {
    return { status: "elevated_concern", reasons };
  }
  if (avgSleepiness >= 4 || avgSleep < 6 || anomalyCount >= 1) {
    return { status: "monitor", reasons };
  }
  return { status: "no_flag", reasons };
}

let guidanceSeq = 0;
const item = (g: Omit<GuidanceItem, "id">): GuidanceItem => ({
  id: `g-${++guidanceSeq}`,
  ...g,
});

function buildGuidance(detections: DetectionResult[]): GuidanceItem[] {
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
