import { useCallback, useEffect, useState } from "react";
import { useHealth } from "../useHealth";
import { useMockHealth } from "../mock/useMockHealth";
import { CREW_ID } from "../config";
import { latestActions, recordAction } from "../../guidance/followup";
import type { CheckInRequest, MissionClockInfo, TaskRequest } from "../../api/client";
import type {
  FollowUpAction,
  Kss,
  MissionTask,
  PipelineResult,
} from "../../shared/types";

export interface CheckInInput {
  heartRate?: number;
  hrv?: number;
  temperature?: number;
  sleepHours?: number;
  sleepiness: Kss;
  mood: 1 | 2 | 3 | 4 | 5;
  wokeAt?: string;
}

export interface TaskInput {
  title: string;
  startsAt: string;
  endsAt: string;
  demand: MissionTask["demand"];
}

export interface HealthData {
  data: PipelineResult | null;
  mission: MissionClockInfo | null;
  refresh: () => Promise<void>;
  error: string | null;
  isMock: boolean;
  guidanceActions: Record<string, FollowUpAction>;
  saveCheckIn: (input: CheckInInput) => Promise<void>;
  saveTask: (task: TaskInput) => Promise<void>;
  saveGuidanceAction: (guidanceId: string, action: FollowUpAction) => Promise<void>;
  /** Load the backend demo scenario into the database. */
  seedDemo: () => Promise<void>;
  wake: string | null;
  setWake: (iso: string | null) => void;
  /** ISO timestamp of the most recent stored check-in. */
  lastCheckIn: string | null;
}

const WAKE_KEY = "cg:last-wake";
const CHECKIN_KEY = "cg:last-checkin";

function readIso(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeIso(key: string, iso: string | null) {
  try {
    if (iso) window.localStorage.setItem(key, iso);
    else window.localStorage.removeItem(key);
  } catch {
    /* storage unavailable — state still updates for this session */
  }
}

/** Map the ritual form onto the backend check-in schema. */
function buildCheckIn(input: CheckInInput): CheckInRequest {
  const now = new Date();
  const request: CheckInRequest = {
    recorded_at: now.toISOString(),
    behavioral: {
      sleepiness_kss: input.sleepiness,
      mood: input.mood,
    },
  };

  if (input.sleepHours !== undefined && input.sleepHours > 0) {
    const parsedWake = input.wokeAt ? new Date(input.wokeAt) : now;
    const end =
      Number.isFinite(parsedWake.getTime()) && parsedWake <= now ? parsedWake : now;
    const start = new Date(end.getTime() - input.sleepHours * 3_600_000);
    request.sleep = {
      sleep_start: start.toISOString(),
      sleep_end: end.toISOString(),
      interruptions: 0,
    };
  }

  const cardiovascular: NonNullable<CheckInRequest["cardiovascular"]> = {};
  if (input.heartRate !== undefined) cardiovascular.heart_rate = input.heartRate;
  if (input.hrv !== undefined) cardiovascular.hrv = input.hrv;
  if (Object.keys(cardiovascular).length > 0) {
    request.cardiovascular = cardiovascular;
  }
  if (input.temperature !== undefined) {
    request.physical = { body_temperature: input.temperature };
  }

  return request;
}

function buildTask(task: TaskInput): TaskRequest {
  return {
    title: task.title,
    task_type: "other",
    start_time: new Date(task.startsAt).toISOString(),
    end_time: new Date(task.endsAt).toISOString(),
    workload_level: task.demand === "demanding" ? "high" : "low",
    is_critical: false,
  };
}

/**
 * Single integration seam for the UI. By default it consumes the backend
 * overview and submits writes through the API; adding `?mock=<scenario>` to
 * the URL swaps in static fixtures with the identical view-model shape.
 */
export function useHealthData(): HealthData {
  const scenario = new URLSearchParams(window.location.search).get("mock");
  const isMock = scenario !== null;

  // Both sources are always mounted so hook order stays stable.
  const real = useHealth(CREW_ID);
  const mock = useMockHealth(scenario);

  const [actions, setActions] = useState<Record<string, FollowUpAction>>({});
  const [wake, setWakeState] = useState<string | null>(() => readIso(WAKE_KEY));
  const [lastCheckIn, setLastCheckIn] = useState<string | null>(() => readIso(CHECKIN_KEY));

  const setWake = useCallback((iso: string | null) => {
    setWakeState(iso);
    writeIso(WAKE_KEY, iso);
  }, []);

  const setLastCheckInIso = useCallback((iso: string | null) => {
    setLastCheckIn(iso);
    writeIso(CHECKIN_KEY, iso);
  }, []);

  // Load guidance follow-up state (real source only).
  useEffect(() => {
    if (isMock) return;
    void latestActions().then(setActions).catch(() => setActions({}));
  }, [isMock, real.data]);

  const refresh = useCallback(async () => {
    if (isMock) await mock.refresh();
    else await real.refresh();
  }, [isMock, mock, real]);

  const saveCheckIn = useCallback(
    async (input: CheckInInput) => {
      const nowIso = new Date().toISOString();
      if (isMock) {
        await new Promise((r) => setTimeout(r, 200));
        setLastCheckInIso(nowIso);
        if (input.wokeAt) setWake(input.wokeAt);
        return;
      }
      await real.submitCheckIn(buildCheckIn(input));
      setLastCheckInIso(nowIso);
      if (input.wokeAt) setWake(input.wokeAt);
    },
    [isMock, real, setLastCheckInIso, setWake],
  );

  const saveTask = useCallback(
    async (task: TaskInput) => {
      if (isMock) {
        await new Promise((r) => setTimeout(r, 200));
        return;
      }
      await real.submitTask(buildTask(task));
    },
    [isMock, real],
  );

  const saveGuidanceAction = useCallback(
    async (guidanceId: string, action: FollowUpAction) => {
      if (isMock) {
        await mock.saveGuidanceAction(guidanceId, action);
        return;
      }
      await recordAction(CREW_ID, guidanceId, action);
      setActions(await latestActions());
    },
    [isMock, mock],
  );

  const seedDemo = useCallback(async () => {
    if (isMock) {
      await new Promise((r) => setTimeout(r, 200));
      return;
    }
    await real.seedDemo();
  }, [isMock, real]);

  const backendWake = isMock ? null : real.wake;
  const resolvedWake =
    backendWake && wake
      ? Date.parse(backendWake) >= Date.parse(wake)
        ? backendWake
        : wake
      : (backendWake ?? wake);

  return {
    data: isMock ? mock.data : real.data,
    mission: isMock ? null : real.mission,
    refresh,
    error: isMock ? null : real.error,
    isMock,
    guidanceActions: isMock ? mock.actions : actions,
    saveCheckIn,
    saveTask,
    saveGuidanceAction,
    seedDemo,
    wake: resolvedWake,
    setWake,
    lastCheckIn: isMock ? lastCheckIn : (real.lastCheckIn ?? lastCheckIn),
  };
}
