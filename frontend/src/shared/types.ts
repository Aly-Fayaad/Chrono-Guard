export type MetricType = "heart_rate" | "hrv" | "temperature" | "sleep_hours";

export type Quality = "valid" | "suspect" | "invalid";

export type MeasurementSource = "manual" | "simulated" | "device";

export interface HealthMeasurement {
  id: string;
  crewId: string;
  type: MetricType;
  value: number;
  unit: string;
  /** ISO timestamp of when the reading was taken. */
  recordedAt: string;
  source: MeasurementSource;
  quality: Quality;
}

export interface CheckIn {
  id: string;
  crewId: string;
  recordedAt: string;
  sleepiness: 1 | 2 | 3 | 4 | 5;
  mood: 1 | 2 | 3 | 4 | 5;
}

export interface MissionTask {
  id: string;
  crewId: string;
  title: string;
  demand: "routine" | "demanding";
  startsAt: string;
  endsAt: string;
}

export type DetectionStatus =
  | "normal"
  | "anomaly"
  | "insufficient_baseline"
  | "data_quality";

export interface AnomalyEvent {
  kind: "sudden" | "sustained";
  explanation: string;
}

export interface DetectionResult {
  metric: MetricType;
  status: DetectionStatus;
  zScore?: number;
  reason?: string;
  event?: AnomalyEvent | null;
}

export type FatigueStatus =
  | "insufficient_data"
  | "no_flag"
  | "monitor"
  | "elevated_concern";

export interface FatigueAssessment {
  status: FatigueStatus;
  reasons: string[];
}

export type GuidanceEvidence = "well_supported" | "limited" | "needs_review";

export interface GuidanceItem {
  id: string;
  title: string;
  why: string;
  evidence: GuidanceEvidence;
  preconditions: string[];
  warnings: string[];
  metric?: MetricType;
}

export type FollowUpAction = "accepted" | "skipped" | "completed";

export interface FollowUpRecord {
  id: string;
  crewId: string;
  guidanceId: string;
  action: FollowUpAction;
  recordedAt: string;
}

export interface PipelineResult {
  series: Record<MetricType, HealthMeasurement[]>;
  detections: DetectionResult[];
  assessment: FatigueAssessment;
  guidance: GuidanceItem[];
  tasks: MissionTask[];
}
