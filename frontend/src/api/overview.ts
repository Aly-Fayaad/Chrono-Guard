import type {
  ApiAssessment,
  ApiAssessmentFactor,
  ApiTask,
  Overview,
} from "./client";
import { buildGuidance } from "../guidance/build";
import type {
  DetectionResult,
  FatigueAssessment,
  HealthMeasurement,
  MetricType,
  MissionTask,
  PipelineResult,
} from "../shared/types";

const METRIC_KEYS: MetricType[] = [
  "heart_rate",
  "hrv",
  "temperature",
  "sleep_hours",
];

function reasonsFor(assessment: ApiAssessment): string[] {
  const reasons = [assessment.summary];
  for (const factor of assessment.contributing_factors) {
    const text = describeFactor(factor);
    if (text && !reasons.includes(text)) reasons.push(text);
  }
  return reasons;
}

function describeFactor(factor: ApiAssessmentFactor): string | null {
  const observed = String(factor.observed ?? "—");
  switch (factor.indicator) {
    case "predicted_kss":
      return `Predicted KSS ${observed} — a group-level model estimate, not a measurement of your sleepiness.`;
    case "baseline_status":
      return `Personal baseline: ${observed}. ${factor.note}`;
    case "latest_sleep_window_h":
      return `Last night: ${observed} h reported in bed (self-reported, not measured total sleep). ${factor.note}.`;
    case "persistent_deviation":
      return `Persistent deviation from your own baseline: ${observed}.`;
    case "workload_equivalent_h":
      return `Upcoming workload equivalent: ${observed} h (modelling extension, not measured impairment).`;
    case "self_reported_kss":
      return `You reported sleepiness ${observed}/9 — reference only; it is not a model input.`;
    case "status_rule":
      return `Status rule (${observed}): ${factor.note}`;
    case "mission_elapsed_time":
      return `Mission clock: ${observed}.`;
    case "sleep_records_available":
      return `Sleep records available: ${observed} night(s).`;
    default:
      return factor.reference
        ? `${factor.indicator}: ${observed} — ${factor.reference}.`
        : `${factor.indicator}: ${observed}.`;
  }
}

function toAssessment(assessment: ApiAssessment | null): FatigueAssessment {
  if (assessment === null) {
    return {
      status: "insufficient_data",
      reasons: [
        "No assessment yet. Submit a check-in so the backend can run the crew-health analysis.",
      ],
    };
  }
  return {
    status: assessment.status,
    reasons: reasonsFor(assessment),
    summary: assessment.summary,
    explanation: assessment.explanation,
    factors: assessment.contributing_factors.map((factor) => ({
      indicator: factor.indicator,
      observed: factor.observed,
      reference: factor.reference,
      note: factor.note,
    })),
    engineVersion: assessment.engine_version,
    createdAt: assessment.created_at,
  };
}

function toMeasurement(
  metric: MetricType,
  row: Overview["series"][MetricType][number],
): HealthMeasurement {
  return {
    id: row.id,
    crewId: row.crew_id,
    type: metric,
    value: row.value,
    unit: row.unit,
    recordedAt: row.recorded_at,
    source: row.source,
    quality: row.quality,
  };
}

function toTask(row: ApiTask): MissionTask {
  return {
    id: row.id,
    crewId: row.crew_id,
    title: row.title,
    demand: row.workload_level === "high" ? "demanding" : "routine",
    startsAt: row.start_time,
    endsAt: row.end_time,
  };
}

/** Convert the backend overview into the view model used by the UI. */
export function toPipelineResult(overview: Overview): PipelineResult {
  const series = {} as Record<MetricType, HealthMeasurement[]>;
  for (const metric of METRIC_KEYS) {
    series[metric] = (overview.series[metric] ?? []).map((row) =>
      toMeasurement(metric, row),
    );
  }

  const detections: DetectionResult[] = overview.detections.map((row) => ({
    metric: row.metric,
    status: row.status,
    zScore: row.z_score ?? undefined,
    reason: row.reason ?? undefined,
    event: row.event ?? null,
  }));

  return {
    series,
    detections,
    assessment: toAssessment(overview.assessment),
    guidance: buildGuidance(detections),
    tasks: overview.tasks.map(toTask),
  };
}
