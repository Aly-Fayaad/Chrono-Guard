import type { FollowUpAction } from "../shared/types";

// Presentation-only state for guidance derived from the overview endpoint.
// It is intentionally not persisted: authoritative mission follow-ups use the
// mission-intelligence API helpers in api/client.ts.
const actions = new Map<string, FollowUpAction>();

export async function latestActions(): Promise<Record<string, FollowUpAction>> {
  return Object.fromEntries(actions);
}

export async function recordAction(
  _crewId: string,
  guidanceId: string,
  action: FollowUpAction,
): Promise<void> {
  actions.set(guidanceId, action);
}
