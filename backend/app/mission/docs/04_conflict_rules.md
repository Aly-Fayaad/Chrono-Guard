# Phase 4 — Rule-Based Conflict Detection

Status: implementation and tests complete for Phase 4. No database schema,
router, service, or file outside `backend/app/mission/` was changed, and
`mission_service.py` was not touched.

Files in this phase:

- `app/mission/conflicts.py` — five pure rule functions plus `detect_conflicts`.
- `app/mission/models.py` — `ConflictType.high_fatigue_critical_task`,
  `Conflict.suggested_action`, computed `Conflict.task_id`, `DataWarning`,
  `ConflictReport`.
- `app/mission/tests/test_conflicts.py` — positive/negative coverage for every
  rule, midnight crossing, deterministic ids, and unknown fatigue.
- `app/mission/tests/test_models.py` — updated for the new required
  `suggested_action` field.

Every number in this document is a **configurable assumption**. The three
sources in `docs/01_references.md` support the *concepts* used by the rules
(sleep opportunity, recovery, circadian trough, workload) but state no numeric
threshold, so no value below is a NASA cut-off.

---

## 1. Output contract

### 1.1 `Conflict`

| Field | Type | Meaning |
| --- | --- | --- |
| `conflict_id` | `str` | Deterministic hash, see 1.2. |
| `rule_id` | `str` | Rule that produced the finding, e.g. `R-RECOVERY-01`. |
| `conflict_type` | `ConflictType` | Category used for grouping and API filtering. |
| `severity` | `Severity` | `low`, `medium`, `high`, or `critical`. |
| `astronaut_id` | `str` | Context owner. |
| `task_ids` | `list[str]` | Every involved task, in schedule order. |
| `task_id` | `str \| None` | Computed convenience field: the first entry of `task_ids`. |
| `affected_start` | `datetime` | Start of the interval the finding is about (UTC). |
| `affected_end` | `datetime` | End of that interval (UTC, may equal the start). |
| `explanation` | `str` | Plain English; names the rule and the values used. |
| `suggested_action` | `str` | Review-oriented wording; never medication, never a claim of improvement. |
| `source_ids` | `list[str]` | Concept anchors from `docs/01_references.md`. |
| `config_keys` | `list[str]` | Configuration keys applied by that rule. |

### 1.2 Deterministic identifier

`conflict_id` is `cf_` followed by the first 16 hexadecimal characters of
SHA-256 over this canonical payload:

```
astronaut_id | sorted(task_ids) joined by "," | conflict_type | rule_id |
affected_start.isoformat() | affected_end.isoformat()
```

The affected interval is part of the hash so two distinct windows for the same
task and rule cannot collide. Re-evaluating the same context produces the same
ids; changing the astronaut, task set, type, rule, or interval changes the id.
Time is never used as a random source.

### 1.3 `ConflictReport`

| Field | Type | Meaning |
| --- | --- | --- |
| `astronaut_id` | `str` | Crew member the report belongs to. |
| `rule_set_version` | `str` | `mission-conflicts/1.0`. |
| `conflicts` | `list[Conflict]` | Sorted by affected start, then severity descending, then conflict id. |
| `data_warnings` | `list[DataWarning]` | Explicit missing-data notes; see Section 4. |
| `config_keys` | `list[str]` | Sorted union of the keys applied by the returned conflicts. |

`DataWarning` carries `rule_id`, `astronaut_id`, optional `task_id`, and a
human-readable `message`. Warnings never replace or suppress a conflict; they
record that a rule was skipped.

`detect_conflicts(context, config=DEFAULT_CONFIG)`:

1. Rejects a context containing another astronaut's task (`ValueError`).
2. Drops `completed` and `cancelled` tasks.
3. Runs the per-task rules in start-time order:
   `sleep_mission_conflict`, `insufficient_recovery`,
   `high_fatigue_before_critical`, `circadian_misalignment`.
4. Runs `workload_overload` once for the whole context.
5. Adds global missing-data warnings, then sorts the output deterministically.

---

## 2. Evidence status of each rule

| Rule | Concept anchor | Concept status | Rule logic | Numeric values |
| --- | --- | --- | --- | --- |
| `R-SLEEP-WINDOW-01` | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` — protect sleep opportunity | Evidence-based concept | Proposed | Configurable assumptions |
| `R-RECOVERY-01` | `NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2` — recovery between demanding periods | Evidence-based concept | Proposed | Configurable assumptions |
| `R-RECOVERY-02` | `NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2` — recovery after restricted sleep | Evidence-based concept | Proposed | Configurable assumptions |
| `R-FATIGUE-CRITICAL-01` | `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures` — fatigue risk before critical work | Evidence-based concept | Proposed | Configurable assumptions |
| `R-WORKLOAD-01` | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` — work overload and error probability | Evidence-based concept | Proposed | Configurable assumptions |
| `R-CIRCADIAN-01` | `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures` — circadian trough | Evidence-based concept | Proposed | Configurable assumptions |

No rule claims to measure an individual's impairment. All outputs are advisory
decision support.

---

## 3. Rules

### 3.1 `sleep_mission_conflict` — `R-SLEEP-WINDOW-01`

**Function:** `sleep_mission_conflict(context, task, config)`

**Logic**

1. Return nothing for `sleep`, `rest`, and `rest_recovery` tasks, because
   occupying a sleep window is their purpose.
2. For each `context.planned_sleep_windows` entry (inferred or explicit), compute
   the exact half-open intersection with the task.
3. Skip the window when the intersection is at or below
   `CONFLICT_OVERLAP_TOLERANCE_MINUTES`.
4. Otherwise emit one conflict whose affected interval is the real intersection.
   Its `explanation` reports the task window, the sleep window, the window
   source, the overlap minutes, and the tolerance.

| Config key | Default | Label |
| --- | --- | --- |
| `CONFLICT_OVERLAP_TOLERANCE_MINUTES` | `0` | configurable assumption |

**Severity:** `critical` when the task is critical (flag or critical priority),
otherwise `high`.

**Sources:** `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2`.

**Edge cases:** a task crossing midnight is intersected correctly by absolute
datetimes, not by clock hour. With no planned window, no conflict is possible
and `detect_conflicts` adds `R-DATA-SLEEP-WINDOW`. A task that overlaps a
planned window also matches the habitual-sleep clock interval in 3.5, so both
`R-SLEEP-WINDOW-01` and `R-CIRCADIAN-01` may appear. They answer different
questions (this specific protected interval versus a recurring clock placement)
and are intentionally not merged.

---

### 3.2 `insufficient_recovery` — `R-RECOVERY-01`, `R-RECOVERY-02`

**Function:** `insufficient_recovery(context, task, config)`

The rule applies only when `task` is demanding. A task is demanding when any of
these holds: `is_critical`, priority `critical`, workload in
`DEMANDING_WORKLOAD_LEVELS`, or required alertness at or above
`CRITICAL_TASK_ALERTNESS_REQUIREMENT`.

**Free time** is computed between two absolute times by subtracting the union of
other work intervals. Intervals are clipped and merged, so overlapping tasks are
never counted twice. Sleep, rest, and recovery tasks are treated as recovery
opportunity, not busy time.

**`R-RECOVERY-01` — between demanding tasks**

1. Find the demanding tasks that end at or before this task's start.
2. Take the latest-ending one as the previous demanding task.
3. Compute free minutes from its end to this task's start.
4. If free minutes `< MIN_RECOVERY_GAP_MINUTES`, emit a conflict covering
   `[previous.end, task.start)` with both task ids.

**`R-RECOVERY-02` — after a short sleep**

1. Take the latest recorded sleep interval.
2. Compare its duration with `CrewProfile.sleep_target_hours × 60`.
3. If the ratio is below `SLEEP_SHORTFALL_REVIEW_RATIO`, compute free minutes
   from sleep end to task start.
4. If free minutes `< MIN_RECOVERY_GAP_MINUTES`, emit a conflict covering
   `[sleep.end, task.start)` with the task id and the sleep values in the
   explanation.

| Config key | Default | Label |
| --- | --- | --- |
| `MIN_RECOVERY_GAP_MINUTES` | `30` | configurable assumption |
| `SLEEP_SHORTFALL_REVIEW_RATIO` | `0.90` | configurable assumption |
| `DEMANDING_WORKLOAD_LEVELS` | `("high",)` | configurable assumption |
| `CRITICAL_TASK_ALERTNESS_REQUIREMENT` | `4` | configurable assumption |

**Severity:** `critical` when the task is critical, otherwise `high`.

**Sources:** `NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2`.

**Interpretation note:** the "free time after a short sleep" check is a
schedule-opportunity check, not a claim that a 30-minute gap repairs sleep loss.
The sources state that recovery from cumulative restriction requires extended
sleep, which is why this rule only asks for review and never claims recovery.

---

### 3.3 `high_fatigue_before_critical` — `R-FATIGUE-CRITICAL-01`

**Function:** `high_fatigue_before_critical(context, task, config)`

**Logic**

1. Return nothing unless the task is critical or high-alertness: `is_critical`,
   priority `critical`, or required alertness at or above
   `CRITICAL_TASK_ALERTNESS_REQUIREMENT`. A missing required-alertness value is
   allowed and does not by itself make the task critical.
2. Read `context.fatigue_signal.level`.
   - `unknown` → **no conflict**; return a `R-FATIGUE-DATA-01` warning.
   - `no_flag` → no conflict.
   - `monitor` → conflict with `high` severity.
   - `elevated_concern` → conflict with `critical` severity.
3. The explanation names the fatigue level, its assessment source, and the task's
   critical flag, priority, required alertness, and threshold.

| Config key | Default | Label |
| --- | --- | --- |
| `CRITICAL_TASK_ALERTNESS_REQUIREMENT` | `4` | configurable assumption |

**Sources:** `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures`.

**Safety note:** subjective fatigue can underestimate objective impairment, so a
`no_flag` result suppresses this rule but is not evidence of safety. Unknown
fatigue is never guessed.

---

### 3.4 `workload_overload` — `R-WORKLOAD-01`

**Function:** `workload_overload(context, config)` (one call per context)

**Logic**

1. Collect open demanding tasks, using the same demanding definition as 3.2.
2. Sort them by start time.
3. For each demanding task as an anchor, define the window
   `[anchor.start, anchor.start + WORKLOAD_WINDOW_HOURS)`.
4. Count demanding tasks that **start** inside the window and sum their demanding
   minutes clipped to the window.
5. Emit a conflict when the count exceeds `MAX_DEMANDING_TASKS_PER_WINDOW` or the
   minutes exceed `MAX_DEMANDING_TASK_HOURS_PER_WINDOW`.
6. Report each maximal task set once: a later window whose task set is a subset
   of an already-reported set is skipped. This keeps consecutive anchors from
   producing near-duplicate findings.

| Config key | Default | Label |
| --- | --- | --- |
| `WORKLOAD_WINDOW_HOURS` | `24` | configurable assumption |
| `MAX_DEMANDING_TASKS_PER_WINDOW` | `3` | configurable assumption |
| `MAX_DEMANDING_TASK_HOURS_PER_WINDOW` | `480` | configurable assumption |
| `DEMANDING_WORKLOAD_LEVELS` | `("high",)` | configurable assumption |
| `CRITICAL_TASK_ALERTNESS_REQUIREMENT` | `4` | configurable assumption |

**Severity:** `high` when only the task-count limit is exceeded; `critical` when
the cumulative-minutes limit is exceeded.

**Affected interval:** the counting window itself, so the report shows which part
of the schedule was assessed.

**Sources:** `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2`.

**Example (matches the code):** four high-workload tasks of 2 h each, starting at
08:00, 10:00, 12:00, and 14:00. The first anchor window is
`08:00 → 08:00 next day`. It contains `4 > 3` demanding tasks and
`4 × 120 = 480 min`, which is not above the 480 min cap. The result is one
`R-WORKLOAD-01` conflict with `high` severity and task ids `high-1 … high-4`.

---

### 3.5 `circadian_misalignment` — `R-CIRCADIAN-01`

**Function:** `circadian_misalignment(context, task, config)`

The rule compares the task's **clock placement** (UTC minute of day, circular so
midnight crossing works) against two configurable windows. It does not use the
calendar date, so a recurring 03:00 pattern is detected even when no sleep window
exists for that particular day.

1. Return nothing for sleep, rest, and recovery tasks.
2. **Habitual sleep period:** if `context.planned_sleep_windows` is non-empty,
   test the task against the clock interval of each window. If no window exists,
   fall back to the configurable protected window
   `PROTECTED_SLEEP_WINDOW_START_HOUR → PROTECTED_SLEEP_WINDOW_END_HOUR`.
3. **Circadian trough:** test the task against the WOCL
   `WOCL_START_HOUR → WOCL_END_HOUR`, expanded on both sides by
   `WOCL_TOLERANCE_MINUTES`.
4. If either check matches, emit one conflict whose explanation lists every
   matched reason.

The "far outside the habitual wake window" requirement is operationalised as the
configured WOCL: it is the deep biological night where alertness is lowest. This
is a deliberately simple model of an individual rhythm.

| Config key | Default | Label |
| --- | --- | --- |
| `WOCL_START_HOUR` | `2` | configurable assumption |
| `WOCL_END_HOUR` | `6` | configurable assumption |
| `WOCL_TOLERANCE_MINUTES` | `30` | configurable assumption |
| `PROTECTED_SLEEP_WINDOW_START_HOUR` | `22` | configurable assumption |
| `PROTECTED_SLEEP_WINDOW_END_HOUR` | `7` | configurable assumption |
| `HABITUAL_SLEEP_MIN_RECORDS` | `3` | configurable assumption |
| `HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES` | `90` | configurable assumption |

The last two keys are listed because they shape the inferred windows supplied by
`adapters.infer_planned_sleep`.

**Severity:** `critical` for a critical task; `high` when required alertness is
at or above `CRITICAL_TASK_ALERTNESS_REQUIREMENT`; otherwise `medium`.

**Sources:** `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures`.

**Assumptions and limitations:** the WOCL is individual, and the data model has no
crew-local time zone. Using fixed UTC clock hours and inferred habitual windows
is a simplifying assumption, not a measurement of circadian phase. When a task
also overlaps a planned window, `R-SLEEP-WINDOW-01` is reported alongside this
rule; see the edge-case note in 3.1.

---

## 4. Data warnings

| Rule id | When | Effect |
| --- | --- | --- |
| `R-FATIGUE-DATA-01` | A critical/high-alertness task is evaluated while fatigue is `unknown`. | No conflict from `R-FATIGUE-CRITICAL-01`; the warning names the task and says no conflict was raised. |
| `R-DATA-SLEEP-WINDOW` | `context.planned_sleep_windows` is empty. | `R-SLEEP-WINDOW-01` cannot run; `R-CIRCADIAN-01` uses the configurable fallback window. Emitted once per report. |
| `R-DATA-SLEEP-RECORD` | No recorded sleep summary is available. | The short-sleep half of `R-RECOVERY-02` is skipped. Emitted once per report. |

Warnings are sorted by rule id, then task id, then message. They contain no
numeric fatigue value and never imply that the missing input was safe.

---

## 5. Safety and scientific framing

1. Outputs are advisory indicators, not a diagnosis or a performance prediction.
   Final authority remains with the crew, flight surgeon, and mission control
   (`NASA-STD-3001-Vol2`, human-in-the-loop principle).
2. Every numeric threshold is a configurable assumption. The sources support the
   risk *relationships* only.
3. No rule recommends medication, treatment, or a clinical action. Suggested
   actions use review-oriented wording and, where a risk reduction is mentioned,
   "may reduce risk under rule X" — never "improves" or "prevents".
4. The module is deterministic and offline. It makes no network calls and
   persists nothing; `mission_service.py` is not wired yet.
5. All times are UTC. Crew-local time zones and individual circadian phase are
   not modelled.
6. A `no_flag` fatigue signal does not prove the absence of risk, because
   subjective fatigue can underestimate objective impairment
   (`NASA-TM-Fatigue-Countermeasures`).

---

## 6. Test coverage

`app/mission/tests/test_conflicts.py` covers:

| Requirement | Tests |
| --- | --- |
| Positive and negative case per rule | 5 rules, at least 2 tests each |
| Midnight crossing | `test_sleep_conflict_handles_a_midnight_crossing_task` |
| Deterministic ids | `test_conflict_id_is_deterministic_for_the_same_inputs`, `test_conflict_id_changes_with_task_or_rule` |
| Unknown fatigue | `test_unknown_fatigue_returns_a_warning_not_a_conflict`, `test_detect_conflicts_reports_unknown_fatigue_without_a_conflict` |
| Config-driven thresholds | overlap tolerance, recovery gap, workload count and minutes |
| Report assembly | ordering, closed-task filtering, missing-data warnings, mixed-crew rejection, determinism |
| Safety wording | `test_all_suggested_actions_are_review_oriented` |

Run from `backend/`:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q
```
