import { db, type QueueItem } from "../data/db";
import {
  ApiError,
  postCheckIn,
  postTask,
  type CheckInRequest,
  type TaskRequest,
} from "../api/client";

export type QueueKind = "checkin" | "task";

interface QueuedCheckIn {
  crewId: string;
  payload: CheckInRequest;
}

interface QueuedTask {
  crewId: string;
  payload: TaskRequest;
}

export interface FlushResult {
  synced: number;
  remaining: number;
}

/** Add a write to the durable offline queue. */
export async function enqueue(
  kind: QueueKind,
  payload: QueuedCheckIn | QueuedTask,
): Promise<void> {
  await db.queue.put({
    id: crypto.randomUUID(),
    kind,
    payload,
    createdAt: new Date().toISOString(),
    attempts: 0,
  });
}

export async function queuedCount(): Promise<number> {
  return db.queue.count();
}

let inFlight: Promise<FlushResult> | null = null;

async function deliver(item: QueueItem): Promise<void> {
  if (item.kind === "checkin") {
    const data = item.payload as QueuedCheckIn;
    await postCheckIn(data.crewId, data.payload);
    return;
  }
  if (item.kind === "task") {
    const data = item.payload as QueuedTask;
    await postTask(data.crewId, data.payload);
    return;
  }
  throw new ApiError(0, `Unknown queued item kind: ${item.kind}`);
}

async function runFlush(): Promise<FlushResult> {
  const items = await db.queue.orderBy("createdAt").toArray();
  let synced = 0;
  for (const item of items) {
    try {
      await deliver(item);
      await db.queue.delete(item.id);
      synced += 1;
    } catch (error) {
      // Keep the entry: a failed write must never be dropped silently.
      await db.queue.update(item.id, {
        attempts: (item.attempts ?? 0) + 1,
        lastError: error instanceof Error ? error.message : "Unknown sync error",
      });
    }
  }
  return { synced, remaining: await db.queue.count() };
}

/**
 * POST every queued write in order. Entries stay in the queue on failure so a
 * later retry (or the browser coming back online) can try again.
 */
export function flush(): Promise<FlushResult> {
  if (inFlight === null) {
    inFlight = runFlush().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

/** Retry the queue every 30 s; `onSynced` refreshes the view after progress. */
export function startAutoSync(onSynced: () => void): () => void {
  const id = window.setInterval(() => {
    void flush().then((result) => {
      if (result.synced > 0) onSynced();
    });
  }, 30_000);
  return () => window.clearInterval(id);
}
