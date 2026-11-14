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
  (import.meta.env.API_BASE_URL as string | undefined)?.replace(/\/+$/, "") ??
  "http://127.0.0.1:8000/api/v1";

const REQUEST_TIMEOUT_MS = 15_000;
const AUTO_PROVISION_CREW =
  (import.meta.env.VITE_AUTO_PROVISION_CREW as string | undefined) === "true";

function requestId(): string {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export class ApiError extends Error {
  /** HTTP status, or 0 when the request never reached the backend. */
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailFromBody(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const record = body as Record<string, unknown>;

  const detail = record.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .filter((message) => message.length > 0);
    if (messages.length > 0) return messages.join("; ");
  } else if (detail !== undefined) {
    return JSON.stringify(detail);
  }

  const error = record.error;
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message: unknown }).message;
    if (typeof message === "string") return message;
  }
  return null;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "X-Request-ID": requestId(),
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
      const parsed = detailFromBody(await response.json());
      if (parsed) detail = parsed;
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

export type ApiQuality = "valid" | "questionable" | "missing";
export type ApiSource = "manual" | "simulated" | "device_import";
export type ApiCheckInSource = "manual" | "device_import";
export type ApiMeasurementType =
  | "heart_rate"
  | "hrv"
  | "systolic_bp"
  | "diastolic_bp"
  | "body_temperature"
  | "mood"
  | "sleepiness_kss"
  | "perceived_stress";

export interface ApiMeasurement {
  id: string;
  crew_id: string;
  type: MetricType;
  value: number;
  unit: string;
  recorded_at: string;
  source: ApiSource;
  quality: ApiQuality;
}

export interface ApiHealthMeasurement {
  id: string;
  crew_id: string;
  checkin_id: string | null;
  type: ApiMeasurementType;
  value: number;
  unit: string;
  recorded_at: string;
  source: ApiSource;
  quality: ApiQuality;
}

export interface ApiSleepRecord {
  id: string;
  crew_id: string;
  checkin_id: string | null;
  sleep_start: string;
  sleep_end: string;
  duration_hours: number;
  interruptions: number;
  source: ApiSource;
  quality: ApiQuality;
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

export interface ApiCrew {
  id: string;
  display_name: string;
  role: string;
  sleep_target_hours: number;
  created_at: string;
}

export interface CrewCreateRequest {
  id?: string;
  display_name: string;
  role: string;
  sleep_target_hours?: number;
}

export interface CheckInRequest {
  recorded_at?: string;
  /** API submissions accept manual or device_import; simulated is seed-only. */
  source?: ApiCheckInSource;
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

export interface ApiCheckInResponse {
  checkin: {
    id: string;
    crew_id: string;
    submitted_at: string;
    notes: string | null;
  };
  measurements: ApiHealthMeasurement[];
  sleep_record: ApiSleepRecord | null;
  assessment: ApiAssessment | null;
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

export interface DashboardMeasurementSummary {
  type: ApiMeasurementType;
  unit: string;
  latest_value: number | null;
  latest_quality: ApiQuality | null;
  latest_recorded_at: string | null;
  valid_count_7d: number;
  questionable_count_7d: number;
  mean_7d: number | null;
}

export interface DashboardSleepSummary {
  last_duration_hours: number | null;
  last_sleep_end: string | null;
  last_quality: ApiQuality | null;
  mean_duration_7d: number | null;
  valid_nights_7d: number;
}

export interface DashboardSummary {
  crew_id: string;
  generated_at: string;
  window_days: number;
  measurements: DashboardMeasurementSummary[];
  sleep: DashboardSleepSummary;
  data_freshness_hours: number | null;
}

export interface AnalysisRunResponse {
  assessment: ApiAssessment | null;
}

export function getOverview(crewId: string): Promise<Overview> {
  return request<Overview>(`/crew/${encodeURIComponent(crewId)}/overview`);
}

export function getCrew(crewId: string): Promise<ApiCrew> {
  return request<ApiCrew>(`/crew/${encodeURIComponent(crewId)}`);
}

export function createCrew(payload: CrewCreateRequest): Promise<ApiCrew> {
  return request<ApiCrew>("/crew", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Create the single-crew demo profile if it does not exist yet.
 *
 * The backend is still authoritative: a 409 means another request created it
 * first, which is the desired end state. Set VITE_AUTO_PROVISION_CREW=false to
 * disable this demo convenience in a managed deployment.
 */
export async function ensureCrew(
  crewId: string,
  displayName = "Luna Park",
  role = "Flight Engineer",
): Promise<boolean> {
  if (!AUTO_PROVISION_CREW) return false;
  try {
    await createCrew({ id: crewId, display_name: displayName, role });
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return false;
    throw error;
  }
}

export function postCheckIn(
  crewId: string,
  payload: CheckInRequest,
): Promise<ApiCheckInResponse> {
  return request<ApiCheckInResponse>(`/crew/${encodeURIComponent(crewId)}/checkins`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function postTask(crewId: string, payload: TaskRequest): Promise<ApiTask> {
  return request<ApiTask>(`/crew/${encodeURIComponent(crewId)}/missions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getDashboardSummary(crewId: string): Promise<DashboardSummary> {
  return request<DashboardSummary>(
    `/crew/${encodeURIComponent(crewId)}/dashboard/summary`,
  );
}

export function getAssessment(
  crewId: string,
  assessmentId: string,
): Promise<ApiAssessment> {
  return request<ApiAssessment>(
    `/crew/${encodeURIComponent(crewId)}/assessments/${encodeURIComponent(assessmentId)}`,
  );
}

export function runAnalysis(
  crewId: string,
  checkinId?: string,
): Promise<AnalysisRunResponse> {
  const query = checkinId ? `?checkin_id=${encodeURIComponent(checkinId)}` : "";
  return request<AnalysisRunResponse>(
    `/crew/${encodeURIComponent(crewId)}/analysis/run${query}`,
    { method: "POST" },
  );
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

// Complete backend contract. Feature pages can use these helpers without
// reimplementing URL escaping, JSON handling, timeouts, or error parsing.
export interface Page<T> { items: T[]; total: number | null; }
export interface ApiCheckInListItem { id: string; crew_id: string; submitted_at: string; notes: string | null; }
export interface ApiCheckInDetail extends ApiCheckInResponse {}
export interface ApiHistory { crew_id: string; [key: string]: unknown; }
export interface ReanalysisResult { crew_id: string; processed: number; succeeded: number; skipped: number; failed: number; insufficient: number; }
export interface DeleteResult { deleted: boolean; id: string; }
export type JsonObject = Record<string, unknown>;

function crewPath(crewId: string): string { return `/crew/${encodeURIComponent(crewId)}`; }
function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const values = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null) values.set(key, String(value));
  const encoded = values.toString();
  return encoded ? `?${encoded}` : "";
}
async function list<T>(path: string): Promise<Page<T>> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { headers: { Accept: "application/json", "X-Request-ID": requestId() }, signal: controller.signal });
    if (!response.ok) {
      let detail = `Request failed (${response.status}).`;
      try { detail = detailFromBody(await response.json()) ?? detail; } catch { /* use status */ }
      throw new ApiError(response.status, detail);
    }
    return { items: await response.json() as T[], total: Number(response.headers.get("X-Total-Count")) || null };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, error instanceof DOMException && error.name === "AbortError" ? "The backend did not respond in time." : "Could not reach the backend. Check that the API is running.");
  } finally { window.clearTimeout(timer); }
}

export function getHealth(): Promise<{ status: string; env: string }> { return request("/health"); }
export function getReadiness(): Promise<{ status: string; database: string; env: string }> { return request("/health/ready"); }
export function listCrew(): Promise<Page<ApiCrew>> { return list("/crew"); }
export function updateCrew(crewId: string, payload: Partial<Pick<CrewCreateRequest, "display_name" | "role" | "sleep_target_hours">>): Promise<ApiCrew> { return request(crewPath(crewId), { method: "PATCH", body: JSON.stringify(payload) }); }
export function deleteCrew(crewId: string): Promise<DeleteResult> { return request(crewPath(crewId), { method: "DELETE" }); }
export function listCheckIns(crewId: string, limit?: number, offset?: number): Promise<Page<ApiCheckInListItem>> { return list(`${crewPath(crewId)}/checkins${query({ limit, offset })}`); }
export function getCheckIn(crewId: string, checkinId: string): Promise<ApiCheckInDetail> { return request(`${crewPath(crewId)}/checkins/${encodeURIComponent(checkinId)}`); }
export function getMeasurementHistory(crewId: string, params: { from?: string; to?: string; limit?: number } = {}): Promise<ApiHistory> { return request(`${crewPath(crewId)}/history/measurements${query(params)}`); }
export function getSleepHistory(crewId: string, params: { from?: string; to?: string; limit?: number } = {}): Promise<ApiHistory> { return request(`${crewPath(crewId)}/history/sleep${query(params)}`); }
export function listTasks(crewId: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<Page<ApiTask>> { return list(`${crewPath(crewId)}/missions${query(params)}`); }
export function getTask(crewId: string, taskId: string): Promise<ApiTask> { return request(`${crewPath(crewId)}/missions/${encodeURIComponent(taskId)}`); }
export function updateTask(crewId: string, taskId: string, payload: Partial<TaskRequest>): Promise<ApiTask> { return request(`${crewPath(crewId)}/missions/${encodeURIComponent(taskId)}`, { method: "PATCH", body: JSON.stringify(payload) }); }
export function deleteTask(crewId: string, taskId: string): Promise<DeleteResult> { return request(`${crewPath(crewId)}/missions/${encodeURIComponent(taskId)}`, { method: "DELETE" }); }
export function listAssessments(crewId: string, limit?: number, offset?: number): Promise<Page<ApiAssessment>> { return list(`${crewPath(crewId)}/assessments${query({ limit, offset })}`); }
export function getLatestAssessment(crewId: string): Promise<ApiAssessment> { return request(`${crewPath(crewId)}/assessments/latest`); }
export function reanalyze(crewId: string): Promise<ReanalysisResult> { return request(`${crewPath(crewId)}/assessments/reanalyze`, { method: "POST" }); }

export function getMissionSchedule(crewId: string, params: Record<string, string | undefined> = {}): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/schedule${query(params)}`); }
export function getMissionIntelOverview(crewId: string, params: Record<string, string | undefined> = {}): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/overview${query(params)}`); }
export function getMissionConflicts(crewId: string, params: Record<string, string | undefined> = {}): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/conflicts${query(params)}`); }
export function getMissionRecommendations(crewId: string, params: Record<string, string | undefined> = {}): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/recommendations${query(params)}`); }
export function runMissionWhatIf(crewId: string, payload: JsonObject): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/what-if`, { method: "POST", body: JSON.stringify(payload) }); }
export function createMissionFollowUp(crewId: string, payload: JsonObject): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/follow-ups`, { method: "POST", body: JSON.stringify(payload) }); }
export function updateMissionFollowUp(crewId: string, followUpId: string, payload: JsonObject): Promise<JsonObject> { return request(`${crewPath(crewId)}/mission-intel/follow-ups/${encodeURIComponent(followUpId)}`, { method: "PATCH", body: JSON.stringify(payload) }); }
