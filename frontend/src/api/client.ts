/**
 * Typed HTTP client for the Chrono-Guard backend.
 *
 * The backend is the single source of truth for mission time, MET, health
 * analysis, detections, and assessments. Everything below is transport plus
 * the API's wire shapes; no health calculations happen here.
 */

import type { DetectionStatus, FatigueStatus, MetricType } from "../shared/types";

/** Base URL of the backend API. Override with VITE_API_BASE_URL at build time. */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "") ??
  "http://127.0.0.1:8000/api/v1";

const REQUEST_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  /** HTTP status, or 0 when the request never reached the backend. */
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    const detail =
      error instanceof DOMException && error.name === "AbortError"
        ? "The backend did not respond in time."
        : "Could not reach the backend. Check that the API is running.";
    throw new ApiError(0, detail);
  } finally {
    window.clearTimeout(timer);
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail !== undefined) detail = JSON.stringify(body.detail);
    } catch {
      /* keep the status-based message */
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

export interface MissionClockInfo {
  as_of: string;
  epoch: string;
  mission_day_hours: number;
  met_hours: number;
  mission_day_index: number;
  mission_local_time_hours: number;
  local_time: string;
  met_label: string;
}

export interface ApiMeasurement {
  id: string;
  crew_id: string;
  type: MetricType;
  value: number;
  unit: string;
  recorded_at: string;
  source: "manual" | "simulated" | "device";
  quality: "valid" | "suspect" | "invalid";
}

export interface ApiDetection {
  metric: MetricType;
  status: DetectionStatus;
  z_score: number | null;
  reason: string | null;
  event: { kind: "sudden" | "sustained"; explanation: string } | null;
}

export interface ApiAssessmentFactor {
  indicator: string;
  observed: unknown;
  reference: string;
  note: string;
}

export interface ApiAssessment {
  id: string;
  crew_id: string;
  checkin_id: string | null;
  status: FatigueStatus;
  summary: string;
  explanation: string;
  contributing_factors: ApiAssessmentFactor[];
  engine_version: string;
  created_at: string;
}

export interface ApiTask {
  id: string;
  crew_id: string;
  title: string;
  task_type: string;
  start_time: string;
  end_time: string;
  workload_level: "low" | "medium" | "high";
  is_critical: boolean;
  notes: string | null;
}

export interface Overview {
  crew_id: string;
  server_time: string;
  analysis_engine: string;
  mission: MissionClockInfo;
  series: Record<MetricType, ApiMeasurement[]>;
  detections: ApiDetection[];
  assessment: ApiAssessment | null;
  tasks: ApiTask[];
  wake: string | null;
  last_check_in: string | null;
}

export interface CheckInRequest {
  recorded_at?: string;
  sleep?: {
    sleep_start: string;
    sleep_end: string;
    interruptions?: number;
  };
  behavioral?: {
    mood?: number;
    sleepiness_kss?: number;
    perceived_stress?: number;
  };
  cardiovascular?: {
    heart_rate?: number;
    hrv?: number;
    systolic_bp?: number;
    diastolic_bp?: number;
  };
  physical?: {
    body_temperature?: number;
  };
  notes?: string;
}

export interface TaskRequest {
  title: string;
  task_type?: string;
  start_time: string;
  end_time: string;
  workload_level?: "low" | "medium" | "high";
  is_critical?: boolean;
  notes?: string | null;
}

export function getOverview(crewId: string): Promise<Overview> {
  return request<Overview>(`/crew/${encodeURIComponent(crewId)}/overview`);
}

export function postCheckIn(
  crewId: string,
  payload: CheckInRequest,
): Promise<unknown> {
  return request(`/crew/${encodeURIComponent(crewId)}/checkins`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function postTask(crewId: string, payload: TaskRequest): Promise<unknown> {
  return request(`/crew/${encodeURIComponent(crewId)}/missions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface SeedResult {
  scenario: string;
  created: boolean;
  crew_id: string;
}

export function seedDemo(scenario = "normal_routine"): Promise<SeedResult> {
  return request<SeedResult>(
    `/demo/seed?scenario=${encodeURIComponent(scenario)}`,
    { method: "POST" },
  );
}
