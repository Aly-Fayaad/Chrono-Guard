/**
 * Mission-time formatting.
 *
 * Epoch and day length come from the backend overview (`mission.epoch` and
 * `mission.mission_day_hours`). The fallback below only covers the first paint
 * before that response arrives; no component owns its own mission constants.
 */

export interface MissionClockConfig {
  epoch: string;
  dayHours: number;
}

const FALLBACK: MissionClockConfig = {
  // Matches the backend default. It is replaced by the first overview response
  // and only prevents an empty clock on the very first paint.
  epoch: "2026-10-30T07:00:00Z",
  dayHours: 24.65,
};

let clock: MissionClockConfig = FALLBACK;

/** Apply the backend-owned mission clock. */
export function setMissionClock(
  mission: { epoch: string; mission_day_hours: number } | null | undefined,
): void {
  if (!mission) {
    clock = FALLBACK;
    return;
  }
  const epochMs = Date.parse(mission.epoch);
  if (!Number.isFinite(epochMs) || !(mission.mission_day_hours > 0)) return;
  clock = { epoch: mission.epoch, dayHours: mission.mission_day_hours };
}

function split(date: Date | string): { day: number; localHours: number } {
  const t = typeof date === "string" ? Date.parse(date) : date.getTime();
  const epochMs = Date.parse(clock.epoch);
  const elapsed = Math.max(0, (t - epochMs) / 3_600_000);
  const day = Math.floor(elapsed / clock.dayHours);
  return { day, localHours: elapsed - day * clock.dayHours };
}

function hms(hours: number): string {
  const total = Math.max(0, Math.floor(hours * 3600));
  // Mission-local hours can legitimately exceed 24 on a 24.65 h day, so the
  // hour field must not wrap at 24. Only minutes/seconds are modulo 60.
  const hh = String(Math.floor(total / 3600)).padStart(2, "0");
  const mm = String(Math.floor(total / 60) % 60).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

/** "D+014" style mission-day label for a timestamp. */
export function metDay(date: Date | string): string {
  const { day } = split(date);
  return `D+${String(day).padStart(3, "0")}`;
}

/** "D+014 07:42" style stamp on the backend mission clock. */
export function metStamp(date: Date | string): string {
  const { day, localHours } = split(date);
  return `D+${String(day).padStart(3, "0")} ${hms(localHours).slice(0, 5)}`;
}

/** "D+014 07:42:10" full mission elapsed time. */
export function metFull(now: Date): string {
  const { day, localHours } = split(now);
  return `D+${String(day).padStart(3, "0")} ${hms(localHours)}`;
}

/** Mission-local hour (0..mission_day_hours) for timeline placement. */
export function missionHour(date: Date | string): number {
  return split(date).localHours;
}

/** Start timestamp of the mission day containing `date` (backend clock). */
export function missionDayStart(date: Date | string): Date {
  const { day } = split(date);
  return new Date(
    Date.parse(clock.epoch) + day * clock.dayHours * 3_600_000,
  );
}

/**
 * UTC clock hour (0..24) for the published 24 h circadian model.
 *
 * The operational mission day is 24.65 h, but the TPM circadian and ultradian
 * equations are published at 24 h / 12 h. Circadian displays therefore stay on
 * the Earth clock; only mission labels use the operational day length.
 */
export function earthClockHour(date: Date | string): number {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600;
}

/** "T−04:32:10" countdown to a future timestamp (negative if past). */
export function countdown(target: Date | string, now: Date): string {
  const t = typeof target === "string" ? Date.parse(target) : target.getTime();
  const diff = t - now.getTime();
  const sign = diff < 0 ? "+" : "−";
  const s = Math.abs(Math.floor(diff / 1000));
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor(s / 60) % 60).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `T${sign}${hh}:${mm}:${ss}`;
}

/** Whole hours between two timestamps. */
export function hoursBetween(a: Date | string, b: Date | string): number {
  const ta = typeof a === "string" ? Date.parse(a) : a.getTime();
  const tb = typeof b === "string" ? Date.parse(b) : b.getTime();
  return Math.max(0, Math.round((tb - ta) / 3_600_000));
}
