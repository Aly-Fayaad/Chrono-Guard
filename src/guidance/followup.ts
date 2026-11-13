import { db } from "../data/db";
import type { FollowUpAction, FollowUpRecord } from "../shared/types";

/** Latest recorded action per guidance item for a crew member. */
export async function latestActions(
  crewId: string,
): Promise<Record<string, FollowUpAction>> {
  const rows = (
    await db.followups.where("crewId").equals(crewId).toArray()
  ).sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
  const actions: Record<string, FollowUpAction> = {};
  for (const r of rows) actions[r.guidanceId] = r.action;
  return actions;
}

export async function recordAction(
  crewId: string,
  guidanceId: string,
  action: FollowUpAction,
): Promise<void> {
  const record: FollowUpRecord = {
    id: crypto.randomUUID(),
    crewId,
    guidanceId,
    action,
    recordedAt: new Date().toISOString(),
  };
  await db.followups.put(record);
}
