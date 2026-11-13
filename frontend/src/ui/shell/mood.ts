import type { FatigueStatus } from "../../shared/types";

/**
 * Maps the fatigue assessment to the Hub's ambient mood.
 * Status is atmosphere, not alarm: color temperature, star density and
 * aurora intensity shift gently. Color is ALWAYS paired with a text
 * label + icon by the callers (accessibility, colour-blind safe).
 */
export interface Mood {
  /** 0..1 — relative star density on the canvas. */
  starDensity: number;
  /** Aurora/nebula tint (css color). */
  auroraColor: string;
  /** 0..1 — aurora intensity. */
  auroraAlpha: number;
  /** Very low-alpha veil wash over the whole scene. */
  veil: string;
  /** Accent used by body rings / UI hints. */
  accent: string;
  /** Human label, always shown next to the color. */
  label: string;
  /** Calm one-line interpretation, second person, no alarmism. */
  hint: string;
}

export const MOOD: Record<FatigueStatus, Mood> = {
  no_flag: {
    starDensity: 1,
    auroraColor: "#3dd6b0",
    auroraAlpha: 0.55,
    veil: "rgba(61, 214, 176, 0.030)",
    accent: "#3dd6b0",
    label: "Within range",
    hint: "Your rhythm looks steady today.",
  },
  monitor: {
    starDensity: 0.8,
    auroraColor: "#f2b84b",
    auroraAlpha: 0.6,
    veil: "rgba(242, 184, 75, 0.038)",
    accent: "#f2b84b",
    label: "Monitor",
    hint: "A few readings drifted — worth a look, not a worry.",
  },
  elevated_concern: {
    starDensity: 0.65,
    auroraColor: "#f26b3a",
    auroraAlpha: 0.72,
    veil: "rgba(242, 107, 58, 0.05)",
    accent: "#f26b3a",
    label: "Review suggested",
    hint: "Let's take this gently — a human review is recommended.",
  },
  insufficient_data: {
    starDensity: 0.5,
    auroraColor: "#6b7684",
    auroraAlpha: 0.25,
    veil: "rgba(107, 120, 132, 0.03)",
    accent: "#6b7684",
    label: "Insufficient data",
    hint: "Log a check-in so the console can learn your rhythm.",
  },
};

/** Fatigue index score shown by the gauge (mirrors ArcGauge). */
export const FATIGUE_SCORE: Record<FatigueStatus, number | null> = {
  insufficient_data: null,
  no_flag: 18,
  monitor: 52,
  elevated_concern: 84,
};
