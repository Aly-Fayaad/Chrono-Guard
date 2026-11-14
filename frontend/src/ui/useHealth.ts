import { useCallback, useEffect, useState } from "react";
import {
  ApiError, ensureCrew, getOverview, postCheckIn, postTask, seedDemo as apiSeedDemo,
  type CheckInRequest, type MissionClockInfo, type Overview, type TaskRequest,
} from "../api/client";
import { toPipelineResult } from "../api/overview";
import type { PipelineResult } from "../shared/types";
import { setMissionClock } from "./lib/time";

export interface HealthSource {
  data: PipelineResult | null;
  mission: MissionClockInfo | null;
  refresh: () => Promise<void>;
  error: string | null;
  lastCheckIn: string | null;
  wake: string | null;
  submitCheckIn: (payload: CheckInRequest) => Promise<void>;
  submitTask: (payload: TaskRequest) => Promise<void>;
  seedDemo: () => Promise<void>;
}

function message(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Something went wrong loading health data.";
}

/** Live backend source. Writes fail visibly rather than being retained locally. */
export function useHealth(crewId: string): HealthSource {
  const [data, setData] = useState<PipelineResult | null>(null);
  const [mission, setMission] = useState<MissionClockInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheckIn, setLastCheckIn] = useState<string | null>(null);
  const [wake, setWake] = useState<string | null>(null);

  const apply = useCallback((overview: Overview) => {
    setMissionClock(overview.mission);
    setData(toPipelineResult(overview));
    setMission(overview.mission);
    setLastCheckIn(overview.last_check_in);
    setWake(overview.wake);
  }, []);
  const refresh = useCallback(async () => {
    try {
      let overview: Overview;
      try { overview = await getOverview(crewId); }
      catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 404) throw cause;
        await ensureCrew(crewId);
        overview = await getOverview(crewId);
      }
      apply(overview);
      setError(null);
    } catch (cause) { setError(message(cause)); }
  }, [apply, crewId]);
  const submitCheckIn = useCallback(async (payload: CheckInRequest) => {
    await postCheckIn(crewId, payload); await refresh();
  }, [crewId, refresh]);
  const submitTask = useCallback(async (payload: TaskRequest) => {
    await postTask(crewId, payload); await refresh();
  }, [crewId, refresh]);
  const seedDemo = useCallback(async () => { await apiSeedDemo(); await refresh(); }, [refresh]);
  useEffect(() => { void refresh(); }, [refresh]);
  return { data, mission, refresh, error, lastCheckIn, wake, submitCheckIn, submitTask, seedDemo };
}
