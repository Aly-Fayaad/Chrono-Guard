import type { FollowUpAction } from "../shared/types";
import { createMissionFollowUp, updateMissionFollowUp, ApiError } from "../api/client";

// Presentation-only state for guidance derived from the overview endpoint.
// Authoritative mission follow-ups are persisted via the mission-intelligence API.
// The in-memory map is kept as a session cache so the UI stays responsive.
const actions = new Map<string, FollowUpAction>();

// In-memory map of guidanceId → server-issued followUpId (for PATCH calls)
const followUpIds = new Map<string, string>();

export async function latestActions(): Promise<Record<string, FollowUpAction>> {
  return Object.fromEntries(actions);
}

export async function recordAction(
  crewId: string,
  guidanceId: string,
  action: FollowUpAction,
): Promise<void> {
  // Update local cache immediately so the UI responds instantly.
  actions.set(guidanceId, action);

  try {
    const existingFollowUpId = followUpIds.get(guidanceId);

    if (!existingFollowUpId) {
      // First action on this guidance item — create a follow-up on the server.
      // The backend links the follow-up to the current recommendation by id.
      const result = await createMissionFollowUp(crewId, {
        recommendation_id: guidanceId,
        // No due_at means open-ended; window uses backend default.
      });
      const record = result as { follow_up?: { follow_up_id?: string } };
      const serverId = record.follow_up?.follow_up_id;
      if (serverId) {
        followUpIds.set(guidanceId, serverId);
        // Now apply the action via PATCH.
        await updateMissionFollowUp(crewId, serverId, { action });
      }
    } else {
      // Follow-up already exists — just update its action.
      await updateMissionFollowUp(crewId, existingFollowUpId, { action });
    }
  } catch (err) {
    // If the backend reports no matching recommendation (404/422) — the
    // guidance item may have been generated client-side only. Fall back to
    // the in-memory store silently so the UI still works.
    if (!(err instanceof ApiError) || (err.status !== 404 && err.status !== 422 && err.status !== 503)) {
      // Unexpected error — log but don't crash the UI.
      console.warn("[ChronoGuard] follow-up sync failed:", err instanceof Error ? err.message : err);
    }
  }
}
