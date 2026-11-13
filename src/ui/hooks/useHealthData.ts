import { useCallback, useEffect, useState } from "react";
import { useHealth } from "../useHealth";
import { useMockHealth } from "../mock/useMockHealth";
import { CREW_ID } from "../config";
import { db } from "../../data/db";
import { ingest } from "../../data/validate";
import { enqueue } from "../../offline/syncQueue";
import { latestActions, recordAction } from "../../guidance/followup";
import type {
  FollowUpAction,
  MissionTask,
  PipelineResult,
} from "../../shared/types";

export interface CheckInInput {
  heartRate?: number;
  hrv?: number;
  temperature?: number;
  sleepHours?: number;
  sleepiness: 1 | 2 | 3 | 4 | 5;
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
  refresh: () => Promise<void>;
  online: boolean;
  queued: number;
  error: string | null;
  isMock: boolean;
  guidanceActions: Record<string, FollowUpAction>;
  saveCheckIn: (input: CheckInInput) => Promise<void>;
  saveTask: (task: TaskInput) => Promise<void>;
  saveGuidanceAction: (guidanceId: string, action: FollowUpAction) => Promise<void>;
  wake: string | null;
  setWake: (iso: string | null) => void;
}

const WAKE_KEY = "cg:last-wake";

function readWake(): string | null {
  try {
    return window.localStorage.getItem(WAKE_KEY);
  } catch {
    return null;
  }
}

/**
 * Single integration seam for the UI. By default it consumes the real
 * `useHealth` pipeline; adding `?mock=<scenario>` to the URL swaps in
 * static fixtures with the identical shape (no pipeline changes needed).
 */
export function useHealthData(): HealthData {
  const scenario = new URLSearchParams(window.location.search).get("mock");
  const isMock = scenario !== null;

  // Both sources are always mounted so hook order stays stable.
  const real = useHealth(CREW_ID);
  const mock = useMockHealth(scenario);

  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<Record<string, FollowUpAction>>({});
  const [wake, setWakeState] = useState<string | null>(readWake);

  const setWake = useCallback((iso: string | null) => {
    setWakeState(iso);
    try {
      if (iso) window.localStorage.setItem(WAKE_KEY, iso);
      else window.localStorage.removeItem(WAKE_KEY);
    } catch {
      /* storage unavailable — state still updates for this session */
    }
  }, []);

  // Load guidance follow-up state (real source only).
  useEffect(() => {
    if (isMock) return;
    void latestActions(CREW_ID).then(setActions).catch(() => setActions({}));
  }, [isMock, real.data]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      if (isMock) await mock.refresh();
      else {
        await real.refresh();
        setActions(await latestActions(CREW_ID));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong loading health data.");
    }
  }, [isMock, mock, real]);

  const saveCheckIn = useCallback(
    async (input: CheckInInput) => {
      if (isMock) {
        await new Promise((r) => setTimeout(r, 200));
        if (input.wokeAt) setWake(input.wokeAt);
        return;
      }
      const now = new Date().toISOString();
      const entries: Array<[string, number | undefined, string]> = [
        ["heart_rate", input.heartRate, "bpm"],
        ["hrv", input.hrv, "ms"],
        ["temperature", input.temperature, "degC"],
        ["sleep_hours", input.sleepHours, "h"],
      ];
      for (const [type, value, unit] of entries) {
        if (value === undefined) continue;
        const existing = await db.measurements
          .where("[crewId+type+recordedAt]")
          .equals([CREW_ID, type, now])
          .toArray();
        const m = await ingest(
          {
            id: crypto.randomUUID(),
            crewId: CREW_ID,
            type: type as Parameters<typeof ingest>[0]["type"],
            value,
            unit,
            recordedAt: now,
            source: "manual",
            quality: "valid",
          },
          existing,
        );
        await db.measurements.put(m);
        await enqueue("measurement", m);
      }
      await db.checkins.put({
        id: crypto.randomUUID(),
        crewId: CREW_ID,
        recordedAt: now,
        sleepiness: input.sleepiness,
        mood: input.mood,
      });
      if (input.wokeAt) setWake(input.wokeAt);
      await refresh();
    },
    [isMock, refresh, setWake],
  );

  const saveTask = useCallback(
    async (task: TaskInput) => {
      if (isMock) {
        await new Promise((r) => setTimeout(r, 200));
        return;
      }
      await db.tasks.put({ id: crypto.randomUUID(), crewId: CREW_ID, ...task });
      await refresh();
    },
    [isMock, refresh],
  );

  const saveGuidanceAction = useCallback(
    async (guidanceId: string, action: FollowUpAction) => {
      if (isMock) {
        await mock.saveGuidanceAction(guidanceId, action);
        return;
      }
      await recordAction(CREW_ID, guidanceId, action);
      setActions(await latestActions(CREW_ID));
      await real.refresh();
    },
    [isMock, mock, real],
  );

  return {
    data: isMock ? mock.data : real.data,
    refresh,
    online: isMock ? mock.online : real.online,
    queued: isMock ? mock.queued : real.queued,
    error,
    isMock,
    guidanceActions: isMock ? mock.actions : actions,
    saveCheckIn,
    saveTask,
    saveGuidanceAction,
    wake,
    setWake,
  };
}
