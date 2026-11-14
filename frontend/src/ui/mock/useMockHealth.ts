import { useMemo, useState } from "react";
import type { FollowUpAction, PipelineResult } from "../../shared/types";
import { mockPipeline, type MockScenario } from "./mockData";

export interface MockHealthSource {
  data: PipelineResult | null;
  refresh: () => Promise<void>;
  /** Guidance follow-up overrides applied on top of the fixture. */
  actions: Record<string, FollowUpAction>;
  saveGuidanceAction: (guidanceId: string, action: FollowUpAction) => Promise<void>;
}

const KNOWN: MockScenario[] = ["normal", "sudden", "sustained", "data-quality"];

/**
 * Mock implementation of the health data source, selected with
 * `?mock=sustained` (also: normal | sudden | data-quality).
 * Returns the same shape the real useHealth hook provides.
 */
export function useMockHealth(scenario: string | null): MockHealthSource {
  const valid: MockScenario | null =
    scenario && (KNOWN as string[]).includes(scenario) ? (scenario as MockScenario) : null;
  const [actions, setActions] = useState<Record<string, FollowUpAction>>({});

  const data = useMemo<PipelineResult | null>(() => {
    if (!valid) return null;
    const base = mockPipeline(valid);
    if (!Object.keys(actions).length) return base;
    return {
      ...base,
      guidance: base.guidance.map((g) =>
        actions[g.id] ? { ...g, ...("status" in g ? {} : {}) } : g,
      ),
    };
  }, [valid, actions]);

  const refresh = async () => {
    /* fixtures are static */
  };

  const saveGuidanceAction = async (guidanceId: string, action: FollowUpAction) => {
    await new Promise((r) => setTimeout(r, 150));
    setActions((prev) => ({ ...prev, [guidanceId]: action }));
  };

  return {
    data: valid ? data : null,
    refresh,
    actions,
    saveGuidanceAction,
  };
}
