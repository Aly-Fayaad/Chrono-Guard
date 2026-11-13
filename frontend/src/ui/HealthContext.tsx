import { createContext, useContext } from "react";
import type { HealthData } from "./hooks/useHealthData";

export type { CheckInInput, TaskInput } from "./hooks/useHealthData";

/**
 * Single health-data context. `App` calls `useHealthData()` once and every
 * page (Hub teasers, Today, Check-in, …) reads the same source so the
 * console stays consistent while navigating.
 */
export const HealthContext = createContext<HealthData | null>(null);

export function useHealth(): HealthData {
  const ctx = useContext(HealthContext);
  if (!ctx) throw new Error("useHealth must be used inside <HealthContext.Provider>");
  return ctx;
}
