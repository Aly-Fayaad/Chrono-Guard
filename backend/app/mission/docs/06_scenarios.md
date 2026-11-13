# Phase 6 — What-if Scenario Analysis

Status: implementation and tests complete for Phase 6. No database schema,
router, service, or file outside `backend/app/mission/` was changed, and
`mission_service.py` was not touched.

Files in this phase:

- `app/mission/scenarios.py` — the five schedule operations and the
  `compare` entry point.
- `app/mission/models.py` — `ConflictTypeMetric`, `WorkloadWindowMetric`,
  `ScheduleMetrics`, and `ScenarioComparison`.
- `app/mission/tests/test_scenarios.py` — operation, validation, immutability,
  metric, determinism, and safety-wording coverage.
- `app/mission/docs/06_scenarios.md` — this document.

Everything is pure and in-memory. A scenario is a temporary edit to one
`AstronautContext`; nothing is written to the database, and the original context
is never mutated. This satisfies the transient what-if requirement FR-08 in
`docs/02_requirements.md`.

The comparison reports schedule-rule metrics only. It never re-predicts fatigue,
never diagnoses, never recommends medication, and never claims that a schedule
change improves fatigue or performance. Final authority remains with the crew,
mission control, and medical staff (`NASA-STD-3001-Vol2`, human-in-the-loop
principle).

---

## 1. Operations

All operations return a new `AstronautContext`. An operation raises `ValueError`
for invalid input rather than guessing a repair.

### `delay_task(context, task_id, minutes)`

Shifts one task later by `minutes`. Both endpoints move, so duration is
preserved. Other tasks are not moved; a resulting overlap is left for `compare`
to report.

Validation:

- `minutes` must be a positive integer.
- The task must exist, belong to the context's crew, and not be completed or
  cancelled.

### `move_task(context, task_id, new_start)`

Moves one task to `new_start` and preserves its duration. Other tasks are not
moved, so a move into an occupied slot is allowed and reported as a conflict.

Validation:

- `new_start` must be timezone-aware.
- The task must exist, belong to the context's crew, and be open.

### `add_recovery_period(context, start, end, *, shift_following_tasks=True, task_id=None, name=...)`

Adds a task with category `rest_recovery`, low workload, low priority, and no
required alertness. It is therefore treated as recovery opportunity by the
Phase 4 rules.

With `shift_following_tasks=True` (default) the block is inserted into the
timeline: every open task starting at or after `start` is pushed forward by the
block duration. This matters because `R-RECOVERY-01` and `R-RECOVERY-02` measure
*free* time, and sleep/rest/recovery tasks are already treated as free
opportunity. A recovery block that merely overlaps existing work therefore does
not create a recovery gap. Inserting and shifting later tasks does.

With `shift_following_tasks=False` the block is added without rescheduling
anything. That is a pure insertion, but it may overlap existing tasks.

The recovery task id is `rec_` followed by the first 16 hexadecimal characters
of SHA-256 over the astronaut id, the interval, and the number of recovery tasks
already present at that interval. Repeated calls on the same context therefore
produce the same id.

Validation:

- `start` and `end` must be timezone-aware and `end > start`.
- The insertion point must not fall inside a task that began earlier; choose a
  boundary between tasks.
- A caller-supplied `task_id` must not already exist.

### `redistribute_workload(context, task_id, new_start, config=DEFAULT_CONFIG)`

Moves one named demanding task to a different slot. This is `move_task` plus a
guard: the task must be demanding under the same definition used by
`R-WORKLOAD-01` (`DEMANDING_WORKLOAD_LEVELS`, critical flag/priority, or
`CRITICAL_TASK_ALERTNESS_REQUIREMENT`).

### `modify_sleep_window(context, new_start, new_end, *, window_index=0)`

Replaces one planned or inferred sleep window. The window's `source` is
preserved; a what-if edit does not invent a new provenance.

Validation:

- There must be at least one window and `window_index` must address it.
- `new_start` and `new_end` must be timezone-aware and `new_end > new_start`.

---

## 2. Comparison entry point

```python
compare(
    original: AstronautContext,
    proposed: AstronautContext,
    config: MissionConfig = DEFAULT_CONFIG,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> ScenarioComparison
```

### Input guard

Both contexts must describe the same astronaut, the same crew profile, the same
recent sleep history, and the same fatigue signal. Only `tasks` (and, for the
sleep-window operation, `planned_sleep_windows`) may differ. This guard keeps the
comparison honest: a fatigue change cannot be presented as a schedule effect,
because fatigue is not an output of this module.

### Evaluation window

By default the window is the earliest to latest boundary among the **original**
context's open tasks and sleep windows. The same window is used for both
schedules. An explicit `window_start`/`window_end` pair overrides the default;
supplying only one endpoint is an error. If the original context has no open task
and no sleep window, `compare` raises `ValueError` instead of inventing a window.

### Output

`ScenarioComparison` contains:

| Field | Meaning |
| --- | --- |
| `original_metrics` | `ScheduleMetrics` for the original context. |
| `proposed_metrics` | `ScheduleMetrics` for the proposed context. |
| `conflict_count_delta` | Proposed total conflicts minus original total conflicts. |
| `resolved_conflicts` | Original conflicts whose deterministic id is absent from the proposed report. |
| `new_conflicts` | Proposed conflicts whose deterministic id is absent from the original report. |
| `summary` | Human-readable rule-metric comparison. |
| `note` | Exactly `"Fatigue was not re-predicted; this comparison reflects schedule rules only."` |
| `config_keys` | Sorted configuration keys used by the comparison. |

Conflict identity is the deterministic Phase 4 `conflict_id`, which covers the
astronaut, sorted task ids, conflict type, rule id, and affected interval. A
changed task or interval therefore appears as one resolved conflict and,
possibly, one new conflict.

---

## 3. Metrics

`ScheduleMetrics` is built for each schedule with `detect_conflicts` and the
Phase 3/4 schedule helpers. It reports:

| Field | Definition |
| --- | --- |
| `conflicts_by_type` | Count, highest severity, and severity distribution per `ConflictType`; types with zero findings are omitted. |
| `total_conflicts` | Number of conflicts in the report. |
| `highest_severity` | Highest severity across all conflicts, if any. |
| `workload_windows` | Maximal `R-WORKLOAD-01` windows with demanding task count, demanding minutes, and whether each limit is exceeded. |
| `total_free_minutes` | Sum of `schedule.free_gaps` with `min_minutes=0` inside the evaluation window. |
| `total_recovery_minutes` | Merged `rest`/`rest_recovery` minutes inside the window. |
| `total_recovery_and_free_minutes` | Sum of the previous two fields. |
| `longest_recovery_gap_minutes` | Longest interval inside the window with no non-protected open task. Sleep, rest, and recovery count as opportunity, matching the recovery rules. |
| `tasks_inside_sleep_windows` | Count of open wake tasks overlapping a sleep window beyond `CONFLICT_OVERLAP_TOLERANCE_MINUTES`, mirroring `R-SLEEP-WINDOW-01`. |
| `task_ids_inside_sleep_windows` | Those task ids, ordered by start time. |
| `fatigue_level`, `fatigue_source` | Copied unchanged from the original context for both schedules. |
| `data_warning_count`, `data_warning_rule_ids` | Missing-data warnings from the conflict report. |

Workload windows mirror the rule's maximal-window logic: a window starts at each
demanding task and spans `WORKLOAD_WINDOW_HOURS`; a task is counted when it
starts inside the window; a window whose task set is a subset of an
already-reported set is skipped. Unlike the rule, every window is returned,
including non-exceeding ones, so the comparison shows the full distribution.

---

## 4. Safety wording

`compare` never states that fatigue, performance, or health improves. The
summary uses the required rule-level wording:

- fewer conflicts: "The proposed schedule has N fewer conflicts under the
  configured rules than the original schedule".
- more conflicts: "The proposed schedule has N more conflicts under the
  configured rules than the original schedule".
- equal counts: "Both schedules have the same number of conflicts under the
  configured rules".

The `note` field is the exact statement:

> Fatigue was not re-predicted; this comparison reflects schedule rules only.

The summary also reports free time, recovery time, and the longest recovery gap
as schedule metrics, explicitly labelled as "not a fatigue prediction". No text
mentions medication, drugs, diagnosis, treatment, prevention, or fatigue
improvement.

---

## 5. Configuration keys

The comparison names the configuration keys its metrics depend on:

| Key | Role |
| --- | --- |
| `CONFLICT_OVERLAP_TOLERANCE_MINUTES` | Sleep-window overlap tolerance. |
| `CRITICAL_TASK_ALERTNESS_REQUIREMENT` | Part of the demanding-task definition. |
| `DEMANDING_WORKLOAD_LEVELS` | Workload levels treated as demanding. |
| `MAX_DEMANDING_TASKS_PER_WINDOW` | Workload task-count limit. |
| `MAX_DEMANDING_TASK_HOURS_PER_WINDOW` | Workload minutes limit. |
| `MIN_RECOVERY_GAP_MINUTES` | Recovery rule threshold named by the conflict report. |
| `SLEEP_SHORTFALL_REVIEW_RATIO` | Short-sleep rule threshold named by the conflict report. |
| `WORKLOAD_WINDOW_HOURS` | Length of a workload counting window. |

All values are configurable assumptions. The sources in `docs/01_references.md`
support the concepts but state no numeric threshold.

---

## 6. Test coverage

`app/mission/tests/test_scenarios.py` covers:

| Requirement | Tests |
| --- | --- |
| Each operation | `delay_task`, `move_task`, `add_recovery_period`, `redistribute_workload`, and `modify_sleep_window` tests. |
| Original not mutated | `test_operations_do_not_mutate_the_original_context`, plus per-operation assertions. |
| Invalid input rejected | unknown/closed/foreign tasks, non-positive delay, naive datetimes, reversed intervals, invalid window index, duplicate id, split insertion point, non-demanding redistribution, changed crew/sleep/fatigue, partial/naive/reversed window, empty original. |
| Recovery conflict reduced | `test_add_recovery_reduces_the_recovery_conflict_count` builds a 10 min gap, inserts a 30 min recovery block, and observes `R-RECOVERY-01` drop from 1 to 0. |
| Rule-based metrics | Conflict grouping, workload windows, free/recovery time, longest recovery gap, tasks inside sleep windows, fatigue copied from the original. |
| Resolved and new conflicts | `test_compare_reports_conflicts_by_type_and_copies_fatigue`, `test_compare_lists_new_conflicts`. |
| Deterministic output | `test_compare_is_deterministic_and_keeps_inputs_unchanged`. |
| Banned claims | `test_banned_claims_are_absent_from_comparison_text` and the exact note assertion. |

Run from `backend/`:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q
```

---

## 7. Limitations

1. A scenario edits one astronaut context only; multi-crew coordination is out
   of scope.
2. The comparison is not a fatigue model. It does not predict sleep debt,
   cognitive performance, or individual impairment.
3. `total_free_minutes` and `total_recovery_minutes` are calendar-window metrics,
   not measures of sleep quality.
4. The default evaluation window comes from the original context. A proposed task
   moved outside that window still contributes to conflict detection, but
   window-based metrics clip it to the original window.
5. All times are UTC. Crew-local time zones and individual circadian phase are
   not modelled.
6. The operations are schedule edits, not approvals. Any resulting plan still
   requires mission, and where indicated medical, review.

---

# Phase 8 — Deterministic Simulation Scenarios (End-to-End)

Status: implementation, tests, and this documentation complete for Phase 8. Every
change is inside `backend/app/mission/`. No database schema, router registration,
service, or file owned by another member was changed, and
`backend/app/services/mission_service.py` was not touched.

Files in this phase:

- `app/mission/scenario_fixtures.py` — six `ScenarioSpec` entries, deterministic
  row builders, `seed_scenario`, `seed_all`, `reset_scenarios`, and the
  `--scenario` / `--reset` command line interface.
- `app/mission/tests/test_scenarios_e2e.py` — one end-to-end API test per
  scenario, plus seed idempotency, reset isolation, synthetic provenance, and
  unknown-key coverage.
- `app/mission/docs/06_scenarios.md` — this document (the Phase 6 what-if
  documentation above is preserved unchanged).

The fixtures are synthetic test data, not NASA data and not AI model output.
They exercise the existing rules; they do not change any threshold. Every numeric
value below is a **configurable assumption** from `app/mission/config.py`, and
the three sources in `docs/01_references.md` support the concepts but state no
numeric cut-off.

---

## 8.1 Common setup

### 8.1.1 Evaluation window

Every scenario uses the same half-open UTC day:

```text
window_start = 2026-11-13T00:00:00Z
window_end   = 2026-11-14T00:00:00Z
```

### 8.1.2 Crew ids

| Scenario key | Crew id | Display name | Role |
| --- | --- | --- | --- |
| `normal_sleep` | `crew-mission-01` | Mira Sol | Commander |
| `sleep_deprivation` | `crew-mission-02` | Tomas Reed | Mission Specialist |
| `high_workload` | `crew-mission-03` | Anya Novak | Flight Engineer |
| `sleep_mission_conflict` | `crew-mission-04` | Idris Kane | Pilot |
| `high_fatigue_before_critical` | `crew-mission-05` | Lea Fontaine | EVA Specialist |
| `recovery_scheduling` | `crew-mission-06` | Noah Brandt | Science Officer |

These ids never overlap the existing demo crews `crew-demo-01` through
`crew-demo-03`. Every crew profile has `sleep_target_hours = 8.0`.

### 8.1.3 Synthetic provenance

The schema has a `source` column only on `SleepRecord` and
`HealthMeasurement`. The fixtures use:

- `SleepRecord.source = MeasurementSource.simulated` (enum value `simulated`).
- `Assessment.engine_version = "synthetic-scenario-fixture/1.0"`. This is a
  fixture label, not an AI model id.
- `Assessment.contributing_factors = [{"source": "simulated",
  "synthetic_test_data": true, "model_output": false, "scenario": "<key>"}]`.
- `Assessment.summary`, `Assessment.explanation`, and `MissionTask.notes` begin
  with the exact marker
  `SYNTHETIC TEST DATA (source=simulated) - not AI model output.`

Scenario 5 uses `AssessmentStatus.elevated_concern` **because the test needs that
input**. The value is seeded by this fixture and is not produced by the AI model.
The docstring and every text field say so.

### 8.1.4 Seeding and reset

Run from `backend/`:

```powershell
# Seed all six scenarios. Existing scenario crews are skipped.
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures

# Delete and recreate all six scenario crews only.
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --reset

# Seed one scenario.
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --scenario normal_sleep

# Recreate one scenario.
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --scenario recovery_scheduling --reset
```

`seed_scenario` is idempotent: if the crew id already exists and `reset` is
false, it returns `{"created": false}` without writing. `reset_scenarios` and
`--reset` delete dependent rows (`ActionHistory`, `Assessment`, `SleepRecord`,
`HealthMeasurement`, `CheckIn`, `MissionTask`) and then the crew profile, but
only for the six `crew-mission-*` ids. No other crew id is queried or deleted.

### 8.1.5 Calling the API manually

The router is implemented in `app/mission/router.py`, registered in
`app/routers/__init__.py`, and mounted under `/api/v1` by `app/main.py`. The
Postman steps below assume the API is running, for example:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
```

Base URL used below: `http://127.0.0.1:8000/api/v1`.

---

## 8.2 Scenario 1 — `normal_sleep` (`crew-mission-01`)

### Input data

| Item | Value |
| --- | --- |
| Assessment | `no_flag`, created `2026-11-13T06:30:00Z` |
| Sleep records | Three nights `2026-11-10/11/12 22:00` to `2026-11-11/12/13 06:00` UTC, 8 h each, `source=simulated` |
| Task 1 | `crew-mission-01-task-science`, "Science sample analysis", `2026-11-13 09:00–10:30`, `science`, `medium` |
| Task 2 | `crew-mission-01-task-exercise`, "Resistance exercise", `2026-11-13 12:00–13:00`, `exercise`, `medium` |
| Task 3 | `crew-mission-01-task-maintenance`, "Habitat maintenance", `2026-11-13 15:00–16:00`, `maintenance`, `low` |

### Expected conflicts

None. Sleep is adequate, gaps are long, all tasks fall outside the inferred
sleep window and the configured WOCL, and no workload limit is reached.

### Expected recommendations

None (`conflict_count = 0`).

### Expected output JSON

`GET /crew/crew-mission-01/mission-intel/conflicts` → `200`:

```json
{
  "crew_id": "crew-mission-01",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [],
  "config_keys": [],
  "data_warnings": []
}
```

`GET /crew/crew-mission-01/mission-intel/recommendations` → `200`:

```json
{
  "crew_id": "crew-mission-01",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "conflict_count": 0,
  "recommendations": [],
  "data_warnings": []
}
```

### Manual Postman test

1. Method `GET`, URL
   `http://127.0.0.1:8000/api/v1/crew/crew-mission-01/mission-intel/conflicts`
   with query params `window_start=2026-11-13T00:00:00Z` and
   `window_end=2026-11-14T00:00:00Z`.
2. Method `GET`, same params on
   `.../crew/crew-mission-01/mission-intel/recommendations`.

Expected: both return `200`; `conflicts` and `recommendations` are empty;
`data_warnings` is empty.

---

## 8.3 Scenario 2 — `sleep_deprivation` (`crew-mission-02`)

### Input data

| Item | Value |
| --- | --- |
| Assessment | `monitor`, created `2026-11-13T06:30:00Z` |
| Sleep records | Four nights `2026-11-10/11/12/13 02:00–06:00` UTC, 4 h each, `source=simulated` |
| Task 1 | `crew-mission-02-task-early`, "Post-wake maintenance", `2026-11-13 06:15–07:15`, `maintenance`, `high` |
| Task 2 | `crew-mission-02-task-day`, "Science sample analysis", `2026-11-13 11:00–12:00`, `science`, `medium` |

Four hours is half of the 8 h sleep target, so the short-sleep ratio is below
`SLEEP_SHORTFALL_REVIEW_RATIO`. Task 1 starts 15 minutes after the recorded wake
time and inside the configured WOCL (`WOCL_START_HOUR` … `WOCL_END_HOUR`,
`WOCL_TOLERANCE_MINUTES`).

### Expected conflicts

| Rule id | Conflict type | Severity | Affected task |
| --- | --- | --- | --- |
| `R-RECOVERY-02` | `insufficient_recovery_gap` | `high` | `crew-mission-02-task-early` |
| `R-FATIGUE-CRITICAL-01` | `high_fatigue_critical_task` | `high` | `crew-mission-02-task-early` |
| `R-CIRCADIAN-01` | `circadian_low_alertness` | `high` | `crew-mission-02-task-early` |

### Expected recommendations

| Recommendation type | Rule id | Countermeasure | Medical review |
| --- | --- | --- | --- |
| `identify_recovery_opportunity` | `R-RECOVERY-02` | `CM-03` | `false` |
| `review_task_timing` | `R-FATIGUE-CRITICAL-01` | `CM-02` | `false` |
| `evaluate_lighting_schedule` | `R-CIRCADIAN-01` | `CM-05` | `false` |

The fatigue signal is `monitor`, not `elevated_concern`, so no recommendation
requires medical review.

### Expected output JSON

Conflict objects below are **abridged to diagnostic fields**; the API also
returns `explanation`, `suggested_action`, `source_ids`, and `config_keys` as
documented in `05_api_contracts.md`.

```json
{
  "crew_id": "crew-mission-02",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {
      "conflict_id": "cf_ad4500e90c099c86",
      "rule_id": "R-RECOVERY-02",
      "conflict_type": "insufficient_recovery_gap",
      "severity": "high",
      "task_ids": ["crew-mission-02-task-early"],
      "affected_start": "2026-11-13T06:00:00Z",
      "affected_end": "2026-11-13T06:15:00Z"
    },
    {
      "conflict_id": "cf_c0fabe14b3015514",
      "rule_id": "R-FATIGUE-CRITICAL-01",
      "conflict_type": "high_fatigue_critical_task",
      "severity": "high",
      "task_ids": ["crew-mission-02-task-early"],
      "affected_start": "2026-11-13T06:15:00Z",
      "affected_end": "2026-11-13T07:15:00Z"
    },
    {
      "conflict_id": "cf_c381967858bdc975",
      "rule_id": "R-CIRCADIAN-01",
      "conflict_type": "circadian_low_alertness",
      "severity": "high",
      "task_ids": ["crew-mission-02-task-early"],
      "affected_start": "2026-11-13T06:15:00Z",
      "affected_end": "2026-11-13T07:15:00Z"
    }
  ],
  "config_keys": [
    "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
    "DEMANDING_WORKLOAD_LEVELS",
    "MIN_RECOVERY_GAP_MINUTES",
    "SLEEP_SHORTFALL_REVIEW_RATIO",
    "WOCL_END_HOUR",
    "WOCL_START_HOUR",
    "WOCL_TOLERANCE_MINUTES"
  ],
  "data_warnings": []
}
```

Recommendations (abridged):

```json
{
  "crew_id": "crew-mission-02",
  "conflict_count": 3,
  "recommendations": [
    {"recommendation_id": "rc_075fa2db054cd37b", "recommendation_type": "identify_recovery_opportunity", "rule_id": "R-RECOVERY-02", "countermeasure_id": "CM-03", "priority": "high", "requires_mission_approval": true, "requires_medical_review": false},
    {"recommendation_id": "rc_aaeb6fa9cdde962d", "recommendation_type": "review_task_timing", "rule_id": "R-FATIGUE-CRITICAL-01", "countermeasure_id": "CM-02", "priority": "high", "requires_mission_approval": true, "requires_medical_review": false},
    {"recommendation_id": "rc_d94d3b82c78e47b6", "recommendation_type": "evaluate_lighting_schedule", "rule_id": "R-CIRCADIAN-01", "countermeasure_id": "CM-05", "priority": "high", "requires_mission_approval": true, "requires_medical_review": false}
  ],
  "data_warnings": []
}
```

### Manual Postman test

1. `GET .../crew/crew-mission-02/mission-intel/conflicts` with the common window.
2. `GET .../crew/crew-mission-02/mission-intel/recommendations` with the common
   window.

Expected: `200`; the conflict types are exactly
`insufficient_recovery_gap`, `high_fatigue_critical_task`,
`circadian_low_alertness`; the recommendation types are exactly
`identify_recovery_opportunity`, `review_task_timing`,
`evaluate_lighting_schedule`; every `requires_medical_review` is `false`.

---

## 8.4 Scenario 3 — `high_workload` (`crew-mission-03`)

### Input data

| Item | Value |
| --- | --- |
| Assessment | `no_flag`, created `2026-11-13T06:30:00Z` |
| Sleep records | The same three 8 h nights as Scenario 1 |
| Task 1 | `crew-mission-03-task-demand-1`, `2026-11-13 08:00–10:00`, `maintenance`, `high` |
| Task 2 | `crew-mission-03-task-demand-2`, `2026-11-13 10:00–12:00`, `maintenance`, `high` |
| Task 3 | `crew-mission-03-task-demand-3`, `2026-11-13 12:00–14:00`, `maintenance`, `high` |
| Task 4 | `crew-mission-03-task-demand-4`, `2026-11-13 14:00–16:00`, `maintenance`, `high` |

Four demanding tasks and 480 demanding minutes exceed
`MAX_DEMANDING_TASKS_PER_WINDOW` and `MAX_DEMANDING_TASK_HOURS_PER_WINDOW` inside
one `WORKLOAD_WINDOW_HOURS` window. Each adjacent pair also has a 0 minute gap,
below `MIN_RECOVERY_GAP_MINUTES`.

### Expected conflicts

| Rule id | Conflict type | Severity | Count |
| --- | --- | --- | --- |
| `R-WORKLOAD-01` | `workload_overload` | `high` | 1 |
| `R-RECOVERY-01` | `insufficient_recovery_gap` | `high` | 3 (one per adjacent pair) |

### Expected recommendations

| Recommendation type | Rule id | Countermeasure | Count |
| --- | --- | --- | --- |
| `redistribute_demanding_tasks` | `R-WORKLOAD-01` | `CM-04` | 1 |
| `identify_recovery_opportunity` | `R-RECOVERY-01` | `CM-03` | 3 |

### Expected output JSON

Abridged to diagnostic fields:

```json
{
  "crew_id": "crew-mission-03",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {"conflict_id": "cf_4b17516cdb98900c", "rule_id": "R-WORKLOAD-01", "conflict_type": "workload_overload", "severity": "high", "task_ids": ["crew-mission-03-task-demand-1", "crew-mission-03-task-demand-2", "crew-mission-03-task-demand-3", "crew-mission-03-task-demand-4"], "affected_start": "2026-11-13T08:00:00Z", "affected_end": "2026-11-14T08:00:00Z"},
    {"conflict_id": "cf_eb21223ad2697c16", "rule_id": "R-RECOVERY-01", "conflict_type": "insufficient_recovery_gap", "severity": "high", "task_ids": ["crew-mission-03-task-demand-1", "crew-mission-03-task-demand-2"], "affected_start": "2026-11-13T10:00:00Z", "affected_end": "2026-11-13T10:00:00Z"},
    {"conflict_id": "cf_6d48e2da106585fd", "rule_id": "R-RECOVERY-01", "conflict_type": "insufficient_recovery_gap", "severity": "high", "task_ids": ["crew-mission-03-task-demand-2", "crew-mission-03-task-demand-3"], "affected_start": "2026-11-13T12:00:00Z", "affected_end": "2026-11-13T12:00:00Z"},
    {"conflict_id": "cf_b8427012022cd595", "rule_id": "R-RECOVERY-01", "conflict_type": "insufficient_recovery_gap", "severity": "high", "task_ids": ["crew-mission-03-task-demand-3", "crew-mission-03-task-demand-4"], "affected_start": "2026-11-13T14:00:00Z", "affected_end": "2026-11-13T14:00:00Z"}
  ],
  "config_keys": [
    "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
    "DEMANDING_WORKLOAD_LEVELS",
    "MAX_DEMANDING_TASKS_PER_WINDOW",
    "MAX_DEMANDING_TASK_HOURS_PER_WINDOW",
    "MIN_RECOVERY_GAP_MINUTES",
    "WORKLOAD_WINDOW_HOURS"
  ],
  "data_warnings": []
}
```

Recommendations (abridged):

```json
{
  "crew_id": "crew-mission-03",
  "conflict_count": 4,
  "recommendations": [
    {"recommendation_id": "rc_a32e6eb2b1d6375e", "recommendation_type": "redistribute_demanding_tasks", "rule_id": "R-WORKLOAD-01", "countermeasure_id": "CM-04", "priority": "high"},
    {"recommendation_id": "rc_6244ff3ab2bcb778", "recommendation_type": "identify_recovery_opportunity", "rule_id": "R-RECOVERY-01", "countermeasure_id": "CM-03", "priority": "high"},
    {"recommendation_id": "rc_df05c9144ce7bf88", "recommendation_type": "identify_recovery_opportunity", "rule_id": "R-RECOVERY-01", "countermeasure_id": "CM-03", "priority": "high"},
    {"recommendation_id": "rc_9bed2e7da89d3628", "recommendation_type": "identify_recovery_opportunity", "rule_id": "R-RECOVERY-01", "countermeasure_id": "CM-03", "priority": "high"}
  ]
}
```

### Manual Postman test

1. `GET .../crew/crew-mission-03/mission-intel/conflicts` with the common window.
2. `GET .../crew/crew-mission-03/mission-intel/recommendations` with the common
   window.

Expected: `200`; conflict types are exactly `workload_overload` and
`insufficient_recovery_gap`, with 1 and 3 occurrences respectively; recommendation
types are exactly `redistribute_demanding_tasks` and
`identify_recovery_opportunity`.

---

## 8.5 Scenario 4 — `sleep_mission_conflict` (`crew-mission-04`)

### Input data

| Item | Value |
| --- | --- |
| Assessment | `no_flag`, created `2026-11-13T06:30:00Z` |
| Sleep records | The same three 8 h nights as Scenario 1, which infer a habitual `22:00–06:00` UTC sleep window |
| Task 1 | `crew-mission-04-task-day`, "Science sample analysis", `2026-11-13 10:00–11:00`, `science`, `medium` |
| Task 2 | `crew-mission-04-task-night`, "Night maintenance", `2026-11-13 23:00` to `2026-11-14 00:00`, `maintenance`, `high` |

Task 2 starts inside the inferred `2026-11-13 22:00` to `2026-11-14 06:00` sleep
window and inside the WOCL.

### Expected conflicts

| Rule id | Conflict type | Severity |
| --- | --- | --- |
| `R-CIRCADIAN-01` | `circadian_low_alertness` | `high` |
| `R-SLEEP-WINDOW-01` | `sleep_window_conflict` | `high` |

### Expected recommendations

| Recommendation type | Rule id | Countermeasure |
| --- | --- | --- |
| `evaluate_lighting_schedule` | `R-CIRCADIAN-01` | `CM-05` |
| `review_sleep_schedule` | `R-SLEEP-WINDOW-01` | `CM-01` |

### Expected output JSON

Abridged to diagnostic fields:

```json
{
  "crew_id": "crew-mission-04",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {"conflict_id": "cf_2cd556d494c5b972", "rule_id": "R-CIRCADIAN-01", "conflict_type": "circadian_low_alertness", "severity": "high", "task_ids": ["crew-mission-04-task-night"], "affected_start": "2026-11-13T23:00:00Z", "affected_end": "2026-11-14T00:00:00Z"},
    {"conflict_id": "cf_bdfa01944156890e", "rule_id": "R-SLEEP-WINDOW-01", "conflict_type": "sleep_window_conflict", "severity": "high", "task_ids": ["crew-mission-04-task-night"], "affected_start": "2026-11-13T23:00:00Z", "affected_end": "2026-11-14T00:00:00Z"}
  ],
  "config_keys": [
    "CONFLICT_OVERLAP_TOLERANCE_MINUTES",
    "HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES",
    "HABITUAL_SLEEP_MIN_RECORDS"
  ],
  "data_warnings": []
}
```

Recommendations (abridged):

```json
{
  "crew_id": "crew-mission-04",
  "conflict_count": 2,
  "recommendations": [
    {"recommendation_id": "rc_1cccce4f8d197c95", "recommendation_type": "evaluate_lighting_schedule", "rule_id": "R-CIRCADIAN-01", "countermeasure_id": "CM-05", "priority": "high"},
    {"recommendation_id": "rc_1f856263ea3422bf", "recommendation_type": "review_sleep_schedule", "rule_id": "R-SLEEP-WINDOW-01", "countermeasure_id": "CM-01", "priority": "high"}
  ]
}
```

### Manual Postman test

1. `GET .../crew/crew-mission-04/mission-intel/conflicts` with the common window.
2. `GET .../crew/crew-mission-04/mission-intel/recommendations` with the common
   window.

Expected: `200`; conflict types are exactly `circadian_low_alertness` and
`sleep_window_conflict`; recommendation types are exactly
`evaluate_lighting_schedule` and `review_sleep_schedule`; both affect only
`crew-mission-04-task-night`.

---

## 8.6 Scenario 5 — `high_fatigue_before_critical` (`crew-mission-05`)

### Input data

| Item | Value |
| --- | --- |
| Assessment | `elevated_concern`, created `2026-11-13T06:30:00Z` |
| Assessment markers | `engine_version = synthetic-scenario-fixture/1.0`; `contributing_factors[0].model_output = false`; summary and explanation carry `SYNTHETIC TEST DATA (source=simulated) - not AI model output.` |
| Sleep records | The same three 8 h nights as Scenario 1 |
| Task 1 | `crew-mission-05-task-eva`, "Critical EVA - solar array inspection", `2026-11-13 09:00–13:00`, `eva`, `high`, `is_critical=true` |
| Task 2 | `crew-mission-05-task-review`, "Procedure review", `2026-11-13 15:00–16:00`, `other`, `low` |

The `elevated_concern` status is a **synthetic fixture input chosen for this
test**. It is not a model result and must not be read as a clinical finding.

### Expected conflicts

| Rule id | Conflict type | Severity |
| --- | --- | --- |
| `R-FATIGUE-CRITICAL-01` | `high_fatigue_critical_task` | `critical` |

### Expected recommendations

| Recommendation type | Rule id | Countermeasure | Medical review |
| --- | --- | --- | --- |
| `review_task_timing` | `R-FATIGUE-CRITICAL-01` | `CM-02` | `true` |

This is the only scenario that sets `requires_medical_review = true`. The advice
is still decision support: it asks for a review, gives no diagnosis, and names
no medication.

### Expected output JSON

The recommendation below is shown in full because it demonstrates the safety
contract. The conflict response is abridged to diagnostic fields.

```json
{
  "crew_id": "crew-mission-05",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {
      "conflict_id": "cf_dcf1eebd43a42ea6",
      "rule_id": "R-FATIGUE-CRITICAL-01",
      "conflict_type": "high_fatigue_critical_task",
      "severity": "critical",
      "task_ids": ["crew-mission-05-task-eva"],
      "affected_start": "2026-11-13T09:00:00Z",
      "affected_end": "2026-11-13T13:00:00Z",
      "suggested_action": "Review the task assignment or timing under rule R-FATIGUE-CRITICAL-01; rescheduling or adding a recovery opportunity may reduce risk. Advisory only; final authority remains with the crew, flight surgeon, and mission control."
    }
  ],
  "config_keys": ["CRITICAL_TASK_ALERTNESS_REQUIREMENT"],
  "data_warnings": []
}
```

```json
{
  "crew_id": "crew-mission-05",
  "conflict_count": 1,
  "recommendations": [
    {
      "recommendation_id": "rc_d4748a91cba30a8a",
      "recommendation_type": "review_task_timing",
      "related_conflict_id": "cf_dcf1eebd43a42ea6",
      "astronaut_id": "crew-mission-05",
      "countermeasure_id": "CM-02",
      "countermeasure_name": "Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough",
      "rule_id": "R-FATIGUE-CRITICAL-01",
      "priority": "critical",
      "requires_mission_approval": true,
      "requires_medical_review": true,
      "warnings": [
        "The recorded fatigue level is 'elevated_concern'; a medical review is flagged for this advisory."
      ],
      "advisory_text": "Consider moving the critical task to a different schedule window or inserting a recovery opportunity before it. Review under rule R-FATIGUE-CRITICAL-01; this may reduce risk under rule R-FATIGUE-CRITICAL-01. This is advisory decision support only; decisions remain with the crew, mission control, and medical staff."
    }
  ],
  "data_warnings": []
}
```

### Manual Postman test

1. `GET .../crew/crew-mission-05/mission-intel/conflicts` with the common window.
2. `GET .../crew/crew-mission-05/mission-intel/recommendations` with the common
   window.

Expected: `200`; exactly one conflict of type `high_fatigue_critical_task` with
severity `critical`; exactly one recommendation of type `review_task_timing`
with `requires_medical_review = true` and `requires_mission_approval = true`.

---

## 8.7 Scenario 6 — `recovery_scheduling` (`crew-mission-06`)

### Input data

| Item | Value |
| --- | --- |
| Assessment | `no_flag`, created `2026-11-13T06:30:00Z` |
| Sleep records | The same three 8 h nights as Scenario 1 |
| Task 1 | `crew-mission-06-task-demanding-a`, "Demanding maintenance A", `2026-11-13 08:00–09:00`, `maintenance`, `high` |
| Task 2 | `crew-mission-06-task-demanding-b`, "Demanding maintenance B", `2026-11-13 09:10–10:10`, `maintenance`, `high` |
| Task 3 | `crew-mission-06-task-day`, "Science sample analysis", `2026-11-13 13:00–14:00`, `science`, `medium` |

The 10 minute gap between Tasks 1 and 2 is below `MIN_RECOVERY_GAP_MINUTES`.

### Expected conflicts

| Rule id | Conflict type | Severity |
| --- | --- | --- |
| `R-RECOVERY-01` | `insufficient_recovery_gap` | `high` |

### Expected recommendations

| Recommendation type | Rule id | Countermeasure |
| --- | --- | --- |
| `identify_recovery_opportunity` | `R-RECOVERY-01` | `CM-03` |

### Expected what-if result

Insert a 30 minute recovery block at `09:00–09:30` UTC with
`shift_following_tasks = true`. This pushes Task 2 to `09:40–10:40` and removes
the recovery conflict. The comparison is rule-based only; fatigue is copied
unchanged from the original context.

### Expected output JSON

Original conflicts (abridged):

```json
{
  "crew_id": "crew-mission-06",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {"conflict_id": "cf_773c6f2af523c905", "rule_id": "R-RECOVERY-01", "conflict_type": "insufficient_recovery_gap", "severity": "high", "task_ids": ["crew-mission-06-task-demanding-a", "crew-mission-06-task-demanding-b"], "affected_start": "2026-11-13T09:00:00Z", "affected_end": "2026-11-13T09:10:00Z"}
  ],
  "config_keys": [
    "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
    "DEMANDING_WORKLOAD_LEVELS",
    "MIN_RECOVERY_GAP_MINUTES"
  ],
  "data_warnings": []
}
```

Original recommendations (abridged):

```json
{
  "crew_id": "crew-mission-06",
  "conflict_count": 1,
  "recommendations": [
    {"recommendation_id": "rc_6fedabfc95e825ce", "recommendation_type": "identify_recovery_opportunity", "rule_id": "R-RECOVERY-01", "countermeasure_id": "CM-03", "priority": "high", "requires_mission_approval": true, "requires_medical_review": false}
  ],
  "data_warnings": []
}
```

What-if comparison (selected fields; the full response also carries both metric
objects and `data_warnings`):

```json
{
  "crew_id": "crew-mission-06",
  "applied_operations": [
    {"index": 0, "type": "add_recovery_period", "task_id": null}
  ],
  "comparison": {
    "conflict_count_delta": -1,
    "original_metrics": {
      "conflicts_by_type": [
        {"conflict_type": "insufficient_recovery_gap", "count": 1, "highest_severity": "high", "severity_counts": {"high": 1}}
      ]
    },
    "proposed_metrics": {"conflicts_by_type": []},
    "resolved_conflicts": [
      {"conflict_type": "insufficient_recovery_gap", "rule_id": "R-RECOVERY-01", "severity": "high"}
    ],
    "new_conflicts": [],
    "summary": "The proposed schedule has 1 fewer conflicts under the configured rules than the original schedule (1 original, 0 proposed; 1 resolved and 0 new conflict(s)). Free time is 1260 min original vs 1230 min proposed; recovery time is 0 min vs 30 min; the longest recovery gap is 600 min vs 570 min. These are rule-based schedule metrics, not a fatigue prediction.",
    "note": "Fatigue was not re-predicted; this comparison reflects schedule rules only."
  }
}
```

### Manual Postman test

1. `GET .../crew/crew-mission-06/mission-intel/conflicts` with the common window.
   Expected: one `insufficient_recovery_gap` conflict under `R-RECOVERY-01`.
2. `POST http://127.0.0.1:8000/api/v1/crew/crew-mission-06/mission-intel/what-if`
   with header `Content-Type: application/json` and body:

```json
{
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "operations": [
    {
      "type": "add_recovery_period",
      "start": "2026-11-13T09:00:00Z",
      "end": "2026-11-13T09:30:00Z",
      "shift_following_tasks": true
    }
  ]
}
```

Expected: `200`; `applied_operations` echoes index 0 and
`add_recovery_period`; `comparison.conflict_count_delta = -1`;
`resolved_conflicts` contains one `insufficient_recovery_gap`; `new_conflicts` is
empty; `comparison.note` is exactly
`Fatigue was not re-predicted; this comparison reflects schedule rules only.`

---

## 8.8 Test coverage

`app/mission/tests/test_scenarios_e2e.py` seeds each scenario and calls the real
router through `TestClient`:

| Test | Asserts |
| --- | --- |
| `test_normal_sleep_has_no_findings` | No conflicts, no recommendations. |
| `test_sleep_deprivation_findings` | The three conflict types and three recommendation types; no medical review. |
| `test_high_workload_findings` | `workload_overload` and `insufficient_recovery_gap`; two recommendation types. |
| `test_sleep_mission_conflict_findings` | `sleep_window_conflict` and `circadian_low_alertness`; two recommendation types. |
| `test_high_fatigue_before_critical_findings` | One `critical` conflict; `review_task_timing` with medical review. |
| `test_recovery_scheduling_what_if_resolves_conflict` | Original conflict and recommendation; what-if delta `-1`, one resolved conflict, no new conflicts, exact note. |
| `test_seed_is_idempotent` | First seed creates, second skips, task counts stay stable. |
| `test_reset_deletes_only_scenario_crews` | All six scenario crews and their rows are removed; `crew-demo-99` survives. |
| `test_fixtures_are_marked_synthetic` | Sleep rows use `simulated`; assessments and tasks carry the marker; `model_output = false`. |
| `test_unknown_scenario_key_is_rejected` | Unknown keys raise `KeyError`; the six supported keys are exact. |

Run from `backend/`:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests/test_scenarios_e2e.py -q
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q
& ".\.venv\Scripts\python.exe" -m pytest -q
```

---

## 8.9 Limitations

1. The fixtures are synthetic and deterministic. They are not NASA datasets and
   must not be presented as operational evidence.
2. Scenario 5 seeds `elevated_concern` to exercise the medical-review flag. This
   is test input, not a model prediction or a clinical finding.
3. The what-if comparison in Scenario 6 re-runs schedule rules only. It does not
   re-predict fatigue and does not claim the change improves fatigue.
4. `Assessment` and `MissionTask` have no `source` column, so provenance is
   carried in text fields, `engine_version`, and `contributing_factors`. A future
   schema change could add a first-class source column.
5. The router is registered in `app/routers/__init__.py`, so manual Postman calls
   work against a running development API. The end-to-end tests also mount it
   explicitly so they remain independent of the registry.
6. Seeded rows are written to whatever database `DATABASE_URL` points at. Run the
   CLI against a development database only; `--reset` is limited to the six
   scenario crew ids but still deletes their rows.

