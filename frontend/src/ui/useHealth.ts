import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  getOverview,
  postCheckIn,
  postTask,
  seedDemo as apiSeedDemo,
  type CheckInRequest,
  type MissionClockInfo,
  type Overview,
  type TaskRequest,
} from "../api/client";
import { toPipelineResult } from "../api/overview";
import type { PipelineResult } from "../shared/types";
import { flush, queuedCount, startAutoSync, enqueue } from "../offline/syncQueue";
import { setMissionClock } from "./lib/time";

export interface HealthSource {
  data: PipelineResult | null;
  mission: MissionClockInfo | null;
  refresh: () => Promise<void>;
  online: boolean;
  queued: number;
  error: string | null;
  lastCheckIn: string | null;
  wake: string | null;
  submitCheckIn: (payload: CheckInRequest) => Promise<void>;
  submitTask: (payload: TaskRequest) => Promise<void>;
  seedDemo: () => Promise<void>;
}

const CACHE_PREFIX = "cg:overview:";

function readCache(crewId: string): Overview | null {
  try {
    const raw = window.localStorage.getItem(`${CACHE_PREFIX}${crewId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Overview;
    return parsed && parsed.mission && parsed.series ? parsed : null;
  } catch {
    return null;
  }
}

function writeCache(crewId: string, overview: Overview): void {
  try {
    window.localStorage.setItem(
      `${CACHE_PREFIX}${crewId}`,
      JSON.stringify(overview),
    );
  } catch {
    /* storage unavailable — the live response still renders */
  }
}

function message(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong loading health data.";
}

/**
 * Real data source: fetches the backend overview and forwards writes to the
 * API. Failed network writes are queued; validation errors are surfaced.
 */
export function useHealth(crewId: string): HealthSource {
  const cached = useRef<Overview | null>(readCache(crewId));
  const [data, setData] = useState<PipelineResult | null>(() =>
    cached.current ? toPipelineResult(cached.current) : null,
  );
  const [mission, setMission] = useState<MissionClockInfo | null>(
    () => cached.current?.mission ?? null,
  );
  const [online, setOnline] = useState(navigator.onLine);
  const [queued, setQueued] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [lastCheckIn, setLastCheckIn] = useState<string | null>(
    () => cached.current?.last_check_in ?? null,
  );
  const [wake, setWake] = useState<string | null>(
    () => cached.current?.wake ?? null,
  );

  useEffect(() => {
    if (cached.current) setMissionClock(cached.current.mission);
  }, []);

  const apply = useCallback((overview: Overview) => {
    setMissionClock(overview.mission);
    setData(toPipelineResult(overview));
    setMission(overview.mission);
    setLastCheckIn(overview.last_check_in);
    setWake(overview.wake);
    writeCache(crewId, overview);
  }, [crewId]);

  const refresh = useCallback(async () => {
    try {
      const overview = await getOverview(crewId);
      apply(overview);
      setError(null);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setQueued(await queuedCount());
    }
  }, [apply, crewId]);

  const submitCheckIn = useCallback(
    async (payload: CheckInRequest) => {
      try {
        await postCheckIn(crewId, payload);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) {
          throw cause;
        }
        await enqueue("checkin", { crewId, payload });
        setQueued(await queuedCount());
        return;
      }
      await refresh();
    },
    [crewId, refresh],
  );

  const submitTask = useCallback(
    async (payload: TaskRequest) => {
      try {
        await postTask(crewId, payload);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) {
          throw cause;
        }
        await enqueue("task", { crewId, payload });
        setQueued(await queuedCount());
        return;
      }
      await refresh();
    },
    [crewId, refresh],
  );

  const seedDemo = useCallback(async () => {
    await apiSeedDemo();
    await flush();
    await refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
    const goOnline = () => {
      setOnline(true);
      void flush().then(async () => {
        setQueued(await queuedCount());
        await refresh();
      });
    };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    const stop = startAutoSync(() => {
      void refresh();
    });
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      stop();
    };
  }, [refresh]);

  return {
    data,
    mission,
    refresh,
    online,
    queued,
    error,
    lastCheckIn,
    wake,
    submitCheckIn,
    submitTask,
    seedDemo,
  };
}
