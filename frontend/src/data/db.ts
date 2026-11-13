import Dexie, { type Table } from "dexie";
import type {
  CheckIn,
  FollowUpRecord,
  HealthMeasurement,
  MissionTask,
} from "../shared/types";

export interface QueueItem {
  id: string;
  kind: string;
  payload: unknown;
  createdAt: string;
  attempts?: number;
  lastError?: string;
}

class ChronoGuardDB extends Dexie {
  measurements!: Table<HealthMeasurement, string>;
  checkins!: Table<CheckIn, string>;
  tasks!: Table<MissionTask, string>;
  followups!: Table<FollowUpRecord, string>;
  queue!: Table<QueueItem, string>;

  constructor() {
    super("chrono-guard");
    this.version(1).stores({
      measurements: "id, crewId, [crewId+type], [crewId+type+recordedAt]",
      checkins: "id, crewId, recordedAt",
      tasks: "id, crewId, startsAt",
      followups: "id, crewId, guidanceId, recordedAt",
      queue: "id, createdAt",
    });
  }
}

export const db = new ChronoGuardDB();
