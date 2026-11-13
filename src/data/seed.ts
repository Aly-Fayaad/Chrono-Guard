import { db } from "./db";
import type { CheckIn, HealthMeasurement, MetricType, MissionTask } from "../shared/types";

export type Scenario = "normal" | "sudden" | "sustained" | "quality";

const CREW = "crew-demo-01";
const DAY_MS = 86_400_000;
/** 2026-11-01 07:00 UTC — demo window start. */
const BASE = Date.UTC(2026, 10, 1, 7);

const HISTORY: Record<MetricType, number[]> = {
  heart_rate: [68, 70, 69, 71, 68, 69, 70, 68, 69, 71, 70, 69, 68, 70],
  hrv: [58, 61, 59, 62, 60, 59, 61, 60, 62, 58, 60, 61, 59, 60],
  temperature: [36.6, 36.7, 36.6, 36.5, 36.6, 36.7, 36.6, 36.6, 36.5, 36.6, 36.7, 36.6, 36.6, 36.5],
  sleep_hours: [7.2, 7.0, 7.5, 6.9, 7.3, 7.1, 7.4, 7.0, 7.2, 6.9, 7.3, 7.1, 7.2, 7.0],
};

const UNITS: Record<MetricType, string> = {
  heart_rate: "bpm",
  hrv: "ms",
  temperature: "degC",
  sleep_hours: "h",
};

/** Most recent 3 days per scenario. */
const RECENT: Record<Scenario, Record<MetricType, number[]>> = {
  normal: { heart_rate: [70, 69, 71], hrv: [60, 59, 61], temperature: [36.6, 36.7, 36.6], sleep_hours: [7.1, 7.2, 7.0] },
  sudden: { heart_rate: [102, 104, 101], hrv: [35, 32, 36], temperature: [37.9, 38.1, 37.8], sleep_hours: [5.2, 5.5, 5.0] },
  sustained: { heart_rate: [88, 90, 92], hrv: [44, 42, 41], temperature: [37.4, 37.5, 37.5], sleep_hours: [5.8, 6.0, 5.9] },
  quality: { heart_rate: [70, 171, 71], hrv: [60, 640, 61], temperature: [36.6, 45.0, 36.6], sleep_hours: [7.1, 0, 7.0] },
};

const SLEEPINESS: Record<Scenario, CheckIn["sleepiness"][]> = {
  normal: [2, 2, 3],
  sudden: [4, 4, 5],
  sustained: [3, 4, 4],
  quality: [3, 2, 3],
};

const MOOD: Record<Scenario, CheckIn["mood"][]> = {
  normal: [4, 4, 3],
  sudden: [2, 2, 1],
  sustained: [3, 2, 2],
  quality: [3, 4, 3],
};

/** Wipes local data and writes a fresh demo dataset for the scenario. */
export async function seedDemo(scenario: Scenario): Promise<void> {
  await Promise.all([
    db.measurements.clear(),
    db.checkins.clear(),
    db.tasks.clear(),
    db.followups.clear(),
  ]);

  const rows: HealthMeasurement[] = [];
  for (const type of Object.keys(HISTORY) as MetricType[]) {
    const values = [...HISTORY[type], ...RECENT[scenario][type]];
    values.forEach((value, i) => {
      const quality =
        scenario === "quality" && i >= HISTORY[type].length && i % 2 === 1
          ? "suspect"
          : "valid";
      rows.push({
        id: `${type}-${i}`,
        crewId: CREW,
        type,
        value,
        unit: UNITS[type],
        recordedAt: new Date(BASE + i * DAY_MS).toISOString(),
        source: "simulated",
        quality,
      });
    });
  }
  await db.measurements.bulkPut(rows);

  const checkins: CheckIn[] = SLEEPINESS[scenario].map((sleepiness, i) => ({
    id: `checkin-${i}`,
    crewId: CREW,
    recordedAt: new Date(BASE + (11 + i) * DAY_MS).toISOString(),
    sleepiness,
    mood: MOOD[scenario][i]!,
  }));
  await db.checkins.bulkPut(checkins);

  const tasks: MissionTask[] = [
    {
      id: "task-1",
      crewId: CREW,
      title: "EVA rock sampling",
      demand: "demanding",
      startsAt: new Date(Date.UTC(2026, 10, 14, 14)).toISOString(),
      endsAt: new Date(Date.UTC(2026, 10, 14, 16)).toISOString(),
    },
    {
      id: "task-2",
      crewId: CREW,
      title: "Payload inventory",
      demand: "routine",
      startsAt: new Date(Date.UTC(2026, 10, 14, 18)).toISOString(),
      endsAt: new Date(Date.UTC(2026, 10, 14, 19, 30)).toISOString(),
    },
    {
      id: "task-3",
      crewId: CREW,
      title: "Resistance exercise block",
      demand: "demanding",
      startsAt: new Date(Date.UTC(2026, 10, 14, 21)).toISOString(),
      endsAt: new Date(Date.UTC(2026, 10, 14, 22)).toISOString(),
    },
  ];
  await db.tasks.bulkPut(tasks);
}
