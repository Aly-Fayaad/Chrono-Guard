import { MISSION_START } from "../config";

/** "D+014" style mission-day label for a timestamp. */
export function metDay(date: Date | string): string {
  const t = typeof date === "string" ? Date.parse(date) : date.getTime();
  const days = Math.floor((t - MISSION_START.getTime()) / 86_400_000);
  return `D+${String(Math.max(days, 0)).padStart(3, "0")}`;
}

/** "D+014 07:42" style stamp. */
export function metStamp(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${metDay(d)} ${hh}:${mm}`;
}

/** "07:42:10" wall-clock segment. */
function hms(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const hh = String(Math.floor(s / 3600) % 24).padStart(2, "0");
  const mm = String(Math.floor(s / 60) % 60).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

/** "D+014 07:42:10" full mission elapsed time. */
export function metFull(now: Date): string {
  const elapsed = now.getTime() - MISSION_START.getTime();
  const days = Math.floor(elapsed / 86_400_000);
  return `D+${String(Math.max(days, 0)).padStart(3, "0")} ${hms(elapsed)}`;
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
