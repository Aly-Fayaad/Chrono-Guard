import { db, type QueueItem } from "../data/db";

/**
 * Local-first sync queue. Entries are recorded offline and drained
 * whenever connectivity returns. There is no server endpoint yet, so
 * `flush` simulates the round-trip and clears the queue.
 */
export async function enqueue(kind: string, payload: unknown): Promise<void> {
  await db.queue.put({
    id: crypto.randomUUID(),
    kind,
    payload,
    createdAt: new Date().toISOString(),
  });
}

export async function queuedCount(): Promise<number> {
  return db.queue.count();
}

export async function flush(): Promise<number> {
  const items: QueueItem[] = await db.queue.toArray();
  if (!items.length) return 0;
  // TODO(teammates): POST the queued items to the crew-health API here.
  await db.queue.bulkDelete(items.map((i) => i.id));
  return items.length;
}

/** Drains the queue periodically while online. Returns a stop function. */
export function startAutoSync(): () => void {
  const tick = () => {
    if (navigator.onLine) void flush();
  };
  const timer = window.setInterval(tick, 30_000);
  return () => window.clearInterval(timer);
}
