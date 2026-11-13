import type { BodyKind } from "../CelestialBody";
import type { HealthData } from "../../hooks/useHealthData";
import { MOOD, FATIGUE_SCORE } from "../mood";
import { countdown, hoursBetween } from "../../lib/time";

export interface HubBodyDef {
  key: string;
  kind: BodyKind;
  name: string;
  /** destination hash route */
  path: string;
  breadcrumb: string;
  ariaLabel: string;
  /** tailwind accent class for the label */
  accentCls: string;
}

/** The six destinations, in tab order. */
export const HUB_BODIES: HubBodyDef[] = [
  {
    key: "today",
    kind: "earth",
    name: "Earth",
    path: "/today",
    breadcrumb: "Today",
    ariaLabel: "Earth — Today status",
    accentCls: "text-earth",
  },
  {
    key: "checkin",
    kind: "moon",
    name: "Moon",
    path: "/check-in",
    breadcrumb: "Check-in",
    ariaLabel: "Moon — Daily check-in ritual",
    accentCls: "text-silver",
  },
  {
    key: "schedule",
    kind: "sun",
    name: "Sun",
    path: "/schedule",
    breadcrumb: "Schedule",
    ariaLabel: "Sun — Mission schedule and circadian cycle",
    accentCls: "text-sun",
  },
  {
    key: "guidance",
    kind: "star",
    name: "Constellation",
    path: "/guidance",
    breadcrumb: "Guidance",
    ariaLabel: "Guiding constellation — Guidance and follow-ups",
    accentCls: "text-nebula",
  },
  {
    key: "restore",
    kind: "aurora",
    name: "Aurora",
    path: "/restore",
    breadcrumb: "Restore",
    ariaLabel: "Aurora — Restore, guided breathing",
    accentCls: "text-aurora",
  },
  {
    key: "earthlink",
    kind: "satellite",
    name: "Relay",
    path: "/earth",
    breadcrumb: "Earth view",
    ariaLabel: "Relay satellite — Earth view and connection to home",
    accentCls: "text-silver",
  },
];

function fmtAgo(iso: string | null, now: Date): string | null {
  if (!iso) return null;
  const h = hoursBetween(iso, now.toISOString());
  if (h <= 0) return "earlier today";
  return `${h} h ago`;
}

/**
 * One-line live teaser per body, computed from the health pipeline.
 * Calm, second-person, never alarmist.
 */
export function bodyTeasers(health: HealthData, now: Date): Record<string, string> {
  const { data, lastCheckIn, wake } = health;
  const t: Record<string, string> = {
    restore: "Guided breathing · 4-6 rhythm",
    earthlink: "Comms relay · view Earth",
  };

  if (!data) {
    t.today = "Syncing your status…";
    t.checkin = "Waiting for health data…";
    t.schedule = "Waiting for health data…";
    t.guidance = "Waiting for health data…";
    return t;
  }

  // Earth — Today status
  const mood = MOOD[data.assessment.status];
  const score = FATIGUE_SCORE[data.assessment.status];
  const anomalyCount = data.detections.filter((d) => d.status === "anomaly").length;
  t.today = `Status: ${mood.label} · Index ${score ?? "—"}` +
    (anomalyCount > 0 ? ` · ${anomalyCount} unusual` : "");

  // Moon — check-in ritual
  const ago = fmtAgo(lastCheckIn, now);
  t.checkin = ago ? `Last check-in ${ago}` : "No check-in yet today";

  // Sun — schedule / circadian
  const upcoming = data.tasks
    .filter((task) => Date.parse(task.startsAt) > now.getTime())
    .sort((a, b) => a.startsAt.localeCompare(b.startsAt))[0];
  t.schedule = upcoming
    ? `Next: ${upcoming.title} · ${countdown(upcoming.startsAt, now)}`
    : wake
      ? `Awake since ${new Date(wake).getUTCHours().toString().padStart(2, "0")}:${new Date(wake).getUTCMinutes().toString().padStart(2, "0")}Z`
      : "No upcoming tasks";

  // Constellation — guidance
  const pending = data.guidance.filter((g) => !health.guidanceActions[g.id]).length;
  t.guidance = pending > 0
    ? `${pending} suggestion${pending > 1 ? "s" : ""} waiting`
    : "All suggestions addressed";

  return t;
}
