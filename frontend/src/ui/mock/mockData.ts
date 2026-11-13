import type {
  DetectionResult,
  FatigueAssessment,
  GuidanceItem,
  HealthMeasurement,
  MetricType,
  MissionTask,
  PipelineResult,
  Quality,
} from "../../shared/types";

export type MockScenario = "normal" | "sudden" | "sustained" | "data-quality";

/**
 * Static fixtures mirroring the shape produced by the real pipeline.
 * Values are hand-picked so each scenario demonstrates one behaviour;
 * deviations shown in tooltips are derived from the declared medians.
 */
// Static chart-fixture spacing only. Mock mode does not run the mission clock;
// live MET/D+ labels always come from the backend overview.
const SAMPLE_SPACING_MS = 86_400_000;
/** 17 synthetic readings for the design fixtures (not mission-clock dates). */
const FIRST = Date.UTC(2026, 9, 28, 7);

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

const RECENT: Record<MockScenario, Record<MetricType, number[]>> = {
  normal: { heart_rate: [70, 69, 71], hrv: [60, 59, 61], temperature: [36.6, 36.7, 36.6], sleep_hours: [7.1, 7.2, 7.0] },
  sudden: { heart_rate: [88, 104, 86], hrv: [55, 33, 57], temperature: [36.6, 36.8, 36.6], sleep_hours: [7.0, 7.1, 6.9] },
  sustained: { heart_rate: [85, 88, 90], hrv: [45, 43, 42], temperature: [37.0, 37.2, 37.4], sleep_hours: [5.9, 5.7, 5.6] },
  "data-quality": { heart_rate: [70, 12, 71], hrv: [60, 640, 61], temperature: [36.6, 45.0, 36.6], sleep_hours: [7.1, 0, 7.0] },
};

/** Declared reference levels for tooltip deviation arithmetic. */
const REFERENCE: Record<MetricType, { median: number; scale: number }> = {
  heart_rate: { median: 69.3, scale: 1.05 },
  hrv: { median: 60.1, scale: 1.15 },
  temperature: { median: 36.62, scale: 0.065 },
  sleep_hours: { median: 7.13, scale: 0.17 },
};

const ISO = (i: number) => new Date(FIRST + i * SAMPLE_SPACING_MS).toISOString();

function buildSeries(
  type: MetricType,
  scenario: MockScenario,
  invalidEveryOther = false,
): HealthMeasurement[] {
  const values = [...HISTORY[type], ...RECENT[scenario][type]];
  return values.map((value, i) => {
    const inRecent = i >= HISTORY[type].length;
    const quality: Quality =
      invalidEveryOther && inRecent && i % 2 === 1 ? "suspect" : "valid";
    return {
      id: `mock-${type}-${i}`,
      crewId: "crew-demo-01",
      type,
      value,
      unit: UNITS[type],
      recordedAt: ISO(i),
      source: "simulated",
      quality,
    };
  });
}

export function deviation(type: MetricType, value: number): number {
  const ref = REFERENCE[type];
  return (value - ref.median) / ref.scale;
}

function detection(
  metric: MetricType,
  status: DetectionResult["status"],
  opts: { z?: number; kind?: "sudden" | "sustained"; reason?: string } = {},
): DetectionResult {
  const fmt = (z: number) => `${Math.abs(z).toFixed(1)}σ`;
  const event = opts.kind
    ? {
        kind: opts.kind,
        explanation:
          opts.kind === "sudden"
            ? `Today's reading is ${fmt(opts.z ?? 0)} from your personal baseline after a stable stretch.`
            : `The last three readings have all drifted ${fmt(opts.z ?? 0)} from your personal baseline.`,
      }
    : null;
  return {
    metric,
    status,
    zScore: opts.z,
    reason: opts.reason,
    event,
  };
}

function series(scenario: MockScenario): Record<MetricType, HealthMeasurement[]> {
  const invalid = scenario === "data-quality";
  return {
    heart_rate: buildSeries("heart_rate", scenario, invalid),
    hrv: buildSeries("hrv", scenario, invalid),
    temperature: buildSeries("temperature", scenario, invalid),
    sleep_hours: buildSeries("sleep_hours", scenario, invalid),
  };
}

const TASKS: MissionTask[] = [
  {
    id: "mock-task-1",
    crewId: "crew-demo-01",
    title: "EVA rock sampling",
    demand: "demanding",
    startsAt: new Date(Date.UTC(2026, 10, 14, 14)).toISOString(),
    endsAt: new Date(Date.UTC(2026, 10, 14, 16)).toISOString(),
  },
  {
    id: "mock-task-2",
    crewId: "crew-demo-01",
    title: "Payload inventory",
    demand: "routine",
    startsAt: new Date(Date.UTC(2026, 10, 14, 18)).toISOString(),
    endsAt: new Date(Date.UTC(2026, 10, 14, 19, 30)).toISOString(),
  },
  {
    id: "mock-task-3",
    crewId: "crew-demo-01",
    title: "Resistance exercise block",
    demand: "demanding",
    startsAt: new Date(Date.UTC(2026, 10, 14, 21)).toISOString(),
    endsAt: new Date(Date.UTC(2026, 10, 14, 22)).toISOString(),
  },
];

const GUIDANCE: GuidanceItem[] = [
  {
    id: "mock-g-1",
    title: "Take a 15-minute low-stimulation rest before your next task",
    why: "Heart-rate and HRV readings are unusual for your baseline; a quiet rest often settles autonomic load.",
    evidence: "limited",
    preconditions: ["Confirm the wearable is seated correctly and re-measure once"],
    warnings: ["If chest pain or breathlessness occurs, contact the flight surgeon"],
    metric: "heart_rate",
  },
  {
    id: "mock-g-2",
    title: "Anchor tonight's sleep window to the station light cycle",
    why: "Sleep duration drifted from your personal range; light-aligned sleep windows support faster re-entrainment.",
    evidence: "well_supported",
    preconditions: ["Dim the panels 45 minutes before the window"],
    warnings: ["Caffeine within 6 h of the window will blunt the effect"],
    metric: "sleep_hours",
  },
  {
    id: "mock-g-3",
    title: "Request a human review of today's readings",
    why: "Flagged patterns benefit from a flight-surgeon look before mission-critical days.",
    evidence: "needs_review",
    preconditions: ["Export the current report from the Today dashboard"],
    warnings: [],
  },
];

function assessment(scenario: MockScenario): FatigueAssessment {
  switch (scenario) {
    case "normal":
      return {
        status: "no_flag",
        reasons: [
          "Sleepiness averaged 2.3/5 over the last 3 check-ins.",
          "Sleep averaged 7.1 h per night over the last 3 nights.",
        ],
      };
    case "sudden":
      return {
        status: "monitor",
        reasons: [
          "Sleepiness averaged 3.7/5 over the last 3 check-ins.",
          "Sleep averaged 7.0 h per night over the last 3 nights.",
          "2 metrics moved outside your personal baseline.",
        ],
      };
    case "sustained":
      return {
        status: "elevated_concern",
        reasons: [
          "Sleepiness averaged 4.3/5 over the last 3 check-ins.",
          "Sleep averaged 5.7 h per night over the last 3 nights.",
          "3 metrics moved outside your personal baseline.",
        ],
      };
    case "data-quality":
      return {
        status: "insufficient_data",
        reasons: [
          "Recent readings were flagged by data-quality checks — re-measure to restore coverage.",
        ],
      };
  }
}

const s = series("normal");
const SCENARIOS: Record<MockScenario, PipelineResult> = {
  normal: {
    series: s,
    detections: [
      detection("heart_rate", "normal", { z: deviation("heart_rate", 71) }),
      detection("hrv", "normal", { z: deviation("hrv", 61) }),
      detection("temperature", "normal", { z: deviation("temperature", 36.6) }),
      detection("sleep_hours", "normal", { z: deviation("sleep_hours", 7.0) }),
    ],
    assessment: assessment("normal"),
    guidance: GUIDANCE,
    tasks: TASKS,
  },
  sudden: {
    series: series("sudden"),
    detections: [
      detection("heart_rate", "anomaly", { z: deviation("heart_rate", 104), kind: "sudden" }),
      detection("hrv", "anomaly", { z: deviation("hrv", 33), kind: "sudden" }),
      detection("temperature", "normal", { z: deviation("temperature", 36.6) }),
      detection("sleep_hours", "normal", { z: deviation("sleep_hours", 6.9) }),
    ],
    assessment: assessment("sudden"),
    guidance: GUIDANCE,
    tasks: TASKS,
  },
  sustained: {
    series: series("sustained"),
    detections: [
      detection("heart_rate", "anomaly", { z: deviation("heart_rate", 90), kind: "sustained" }),
      detection("hrv", "anomaly", { z: deviation("hrv", 42), kind: "sustained" }),
      detection("temperature", "anomaly", { z: deviation("temperature", 37.4), kind: "sustained" }),
      detection("sleep_hours", "anomaly", { z: deviation("sleep_hours", 5.6), kind: "sustained" }),
    ],
    assessment: assessment("sustained"),
    guidance: GUIDANCE,
    tasks: TASKS,
  },
  "data-quality": {
    series: series("data-quality"),
    detections: [
      detection("heart_rate", "data_quality", {
        reason: "Recent readings were flagged by quality checks — re-measure before trusting the trend.",
      }),
      detection("hrv", "data_quality", {
        reason: "Recent readings were flagged by quality checks — re-measure before trusting the trend.",
      }),
      detection("temperature", "data_quality", {
        reason: "Recent readings were flagged by quality checks — re-measure before trusting the trend.",
      }),
      detection("sleep_hours", "data_quality", {
        reason: "Recent readings were flagged by quality checks — re-measure before trusting the trend.",
      }),
    ],
    assessment: assessment("data-quality"),
    guidance: GUIDANCE,
    tasks: TASKS,
  },
};

export function mockPipeline(scenario: MockScenario): PipelineResult {
  return SCENARIOS[scenario];
}
