import { useCallback, useEffect, useState } from "react";
import { runPipeline, type PipelineResult } from "../pipeline";
import { flush, queuedCount, startAutoSync } from "../offline/syncQueue";

export function useHealth(crewId: string) {
  const [data, setData] = useState<PipelineResult | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [queued, setQueued] = useState(0);

  const refresh = useCallback(async () => {
    setData(await runPipeline(crewId));
    setQueued(await queuedCount());
  }, [crewId]);

  useEffect(() => {
    void refresh();
    const on = () => {
      setOnline(true);
      void flush().then(refresh);
    };
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    const stop = startAutoSync();
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
      stop();
    };
  }, [refresh]);

  return { data, refresh, online, queued };
}
