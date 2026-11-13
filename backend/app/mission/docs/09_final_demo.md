# Phase 9 — Final Demo Script (Mission Intelligence)

Status: **documentation only**. This is the run-of-show for the Person 4
(Mission Intelligence) demo. It uses only implemented behaviour and the exact
Phase 8 fixture data. It adds no endpoints and changes no contract.

> **Say this once, early:** this is advisory decision support. It does not
> diagnose, does not measure impairment, does not recommend medication, and does
> not change a mission task. A schedule comparison is rule-based, not a fatigue
> prediction.

---

## 1. Demo at a glance

| Item | Value |
| --- | --- |
| Target length | 9–12 minutes (6 scenes + limitations) |
| Audience | Project reviewers, Person 1/2/3, supervisor |
| Live surface | FastAPI + Postman; UI screens per `07_ux_spec.md` if Person 1 has them |
| Data | Six deterministic synthetic scenarios (`scenario_fixtures.py`) |
| Writes | Follow-ups only, in process memory |
| Reset | Re-seed the database, or restart the API to clear follow-ups |
| Exact window | `2026-11-13T00:00:00Z` → `2026-11-14T00:00:00Z` (UTC) |

### Scene order

| # | Scene | Crew | Screen | Time |
| --- | --- | --- | --- | --- |
| 1 | Baseline: no findings, not a clearance | `crew-mission-01` | Overview + Conflicts | 1 min |
| 2 | Short sleep + early demanding task | `crew-mission-02` | Fatigue Alerts + Conflicts | 2 min |
| 3 | Workload concentration | `crew-mission-03` | Conflicts + Recommendations | 2 min |
| 4 | Task inside the sleep window | `crew-mission-04` | Mission Calendar | 1.5 min |
| 5 | Critical task + elevated concern | `crew-mission-05` | Recommendations + medical-review flag | 2 min |
| 6 | What-if and follow-up lifecycle | `crew-mission-06` | What-if + Follow-ups | 2.5 min |
| 7 | Limitations slide | — | Slide | 1 min |

---

## 2. Preflight (do this 10 minutes before)

### 2.1 Router registration check

The mission router is registered in `backend/app/routers/__init__.py` and
mounted by `app/main.py` under `/api/v1`. No edit is needed before the demo.

Verify it is live while the API is running:

```powershell
$base = "http://127.0.0.1:8000/api/v1"
try {
  Invoke-RestMethod -Method Get -Uri "$base/crew/crew-mission-01/mission-intel/conflicts?window_start=2026-11-13T00:00:00Z&window_end=2026-11-14T00:00:00Z" | ConvertTo-Json -Depth 6
} catch {
  $_.ErrorDetails.Message
}
```

Expected: `200` with `"conflicts": []`. A plain `{"detail":"Not Found"}` means the
running server is an older process that predates the registration — restart
uvicorn. A `crew_not_found` envelope means the router is mounted but the scenario
data is not seeded.

### 2.2 Environment and data

Run everything from `backend/` in Windows PowerShell:

```powershell
# 1. Confirm the mission suite is green.
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q

# 2. Recreate the six scenario crews (only crew-mission-* rows are touched).
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --reset

# 3. Start the API.
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
```

Expected test result: `205 passed, 1 warning` (the warning is the pre-existing
Starlette `TestClient` deprecation).

Expected seed output: one line per scenario, each `created` or `reset`. The six
crews are listed in `06_scenarios.md` §8.1.2.

### 2.3 Shared variables

Use a second terminal:

```powershell
$base = "http://127.0.0.1:8000/api/v1"
$ws = "2026-11-13T00:00:00Z"
$we = "2026-11-14T00:00:00Z"
```

> Every scenario request must send both `window_start` and `window_end`.
> Omitting them defaults to “now”, which does not match the fixed fixtures and
> produces different ids and findings.

### 2.4 Provenance reminder

Scenario 5’s `elevated_concern` value is **seeded synthetic input**, not AI model
output. Its assessment row carries
`engine_version = synthetic-scenario-fixture/1.0`, its
`contributing_factors[0].model_output` is `false`, and its text fields begin with
`SYNTHETIC TEST DATA (source=simulated) - not AI model output.`

Say this once during Scene 5.

---

## 3. Scene scripts

### Scene 1 — Baseline: no findings is not a clearance (`crew-mission-01`)

**Goal:** show that the system is explicit about what it did and did not
evaluate.

**PowerShell**

```powershell
$c = "crew-mission-01"
$overview = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/overview?window_start=$ws&window_end=$we"
$conflicts = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/conflicts?window_start=$ws&window_end=$we"

"crew: $($overview.crew.display_name)"
"fatigue: $($overview.health.fatigue_signal.level)"
"tasks: $($overview.upcoming_tasks.Count)"
"conflicts: $($conflicts.conflicts.Count)"
"recommendations: $($overview.recommendation_count)"
"warnings: $($conflicts.data_warnings.Count)"
```

**Expected**

```text
crew: Mira Sol
fatigue: no_flag
tasks: 3
conflicts: 0
recommendations: 0
warnings: 0
```

**Screen:** Health–Mission Overview → no findings; Schedule Conflicts → empty
state.

**Say:** “No conflicts under the configured rules in this window. That is not a
safety clearance — it means these rules, with this data, found nothing.”

**Do not say:** “The crew is safe / cleared / rested.”

---

### Scene 2 — Short sleep before an early demanding task (`crew-mission-02`)

**Goal:** show one input producing three explainable rule findings and three
advisory countermeasures, none requiring medical review.

**PowerShell**

```powershell
$c = "crew-mission-02"
$conflicts = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/conflicts?window_start=$ws&window_end=$we"
$recs = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/recommendations?window_start=$ws&window_end=$we"

$conflicts.conflicts | Select-Object rule_id, conflict_type, severity, affected_start, affected_end | Format-Table -AutoSize
$recs.recommendations | Select-Object recommendation_type, rule_id, countermeasure_id, priority, requires_medical_review | Format-Table -AutoSize
```

**Expected conflicts (3)**

| Rule | Type | Severity |
| --- | --- | --- |
| `R-RECOVERY-02` | `insufficient_recovery_gap` | `high` |
| `R-FATIGUE-CRITICAL-01` | `high_fatigue_critical_task` | `high` |
| `R-CIRCADIAN-01` | `circadian_low_alertness` | `high` |

**Expected recommendations (3)**

| Type | Countermeasure | Medical review |
| --- | --- | --- |
| `identify_recovery_opportunity` | `CM-03` | `false` |
| `review_task_timing` | `CM-02` | `false` |
| `evaluate_lighting_schedule` | `CM-05` | `false` |

**Screen:** Fatigue Alerts → signal `monitor`, three related cards; then
Recommendations.

**Say:** “Four short nights are seeded data. The fatigue input is the categorical
assessment `monitor`, not a score. The rules flag recovery, timing, and
circadian placement. Each advisory says ‘may reduce risk under rule …’.”

**Do not say:** “The crew is impaired.” This scenario has no medical-review flag
because the input is `monitor`, not `elevated_concern`.

---

### Scene 3 — Workload concentration (`crew-mission-03`)

**Goal:** show aggregate workload plus one finding per adjacent pair, and the
recommendation cap.

**PowerShell**

```powershell
$c = "crew-mission-03"
$conflicts = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/conflicts?window_start=$ws&window_end=$we"
$recs = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/recommendations?window_start=$ws&window_end=$we"

"conflicts: $($conflicts.conflicts.Count)"
$conflicts.conflicts | Group-Object conflict_type | Select-Object Name, Count | Format-Table -AutoSize
"recommendations: $($recs.recommendations.Count)"
$recs.recommendations | Group-Object recommendation_type | Select-Object Name, Count | Format-Table -AutoSize
```

**Expected**

```text
conflicts: 4
workload_overload          1
insufficient_recovery_gap  3

recommendations: 4
redistribute_demanding_tasks  1
identify_recovery_opportunity 3
```

**Screen:** Schedule Conflicts → 4 high-severity findings; Recommendations → 4
advisories.

**Say:** “Four demanding tasks, 480 demanding minutes, zero-minute gaps. The
workload rule fires once; the recovery rule fires per adjacent pair. Nothing is
auto-moved — `requires_mission_approval` is `true` on every advisory.”

**Point out:** the three recovery findings are not duplicate noise; each names a
different task pair in `task_ids`.

---

### Scene 4 — Task inside the protected sleep window (`crew-mission-04`)

**Goal:** show the calendar/sleep-band story and the difference between a sleep
window and a circadian finding.

**PowerShell**

```powershell
$c = "crew-mission-04"
$schedule = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/schedule?view=daily&date=2026-11-13"
$conflicts = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/conflicts?window_start=$ws&window_end=$we"

$schedule.planned_sleep_windows | Format-List
$schedule.tasks | Select-Object name, start_time, end_time | Format-Table -AutoSize
$conflicts.conflicts | Select-Object rule_id, conflict_type, severity, task_id | Format-Table -AutoSize
```

**Expected**

```text
Sleep window: 2026-11-13T22:00:00Z → 2026-11-14T06:00:00Z (480 min, inferred_habitual_sleep)

Rule                    Type                     Severity  Task
R-CIRCADIAN-01          circadian_low_alertness  high      crew-mission-04-task-night
R-SLEEP-WINDOW-01       sleep_window_conflict    high      crew-mission-04-task-night
```

**Screen:** Mission Calendar → sleep band behind the 23:00 “Night maintenance”
block, two markers; Conflicts → two cards.

**Say:** “The 23:00 task overlaps the inferred habitual sleep window and falls in
the configured Window of Circadian Low. Two different rules, two different
reasons, same task. The sleep band is inferred from sleep records, not a mission
planning input.”

---

### Scene 5 — Critical task with elevated concern (`crew-mission-05`)

**Goal:** show the highest severity, the medical-review flag, and the safety
wording. This is the most sensitive scene.

**PowerShell**

```powershell
$c = "crew-mission-05"
$overview = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/overview?window_start=$ws&window_end=$we"
$recs = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/recommendations?window_start=$ws&window_end=$we"

"fatigue: $($overview.health.fatigue_signal.level)"
"source: $($overview.health.fatigue_signal.source)"
"model_output: $($overview.health.fatigue_signal.contributing_factors[0].model_output)"
$recs.recommendations[0] | Select-Object recommendation_type, countermeasure_id, priority, requires_mission_approval, requires_medical_review, warnings | Format-List
$recs.recommendations[0].advisory_text
```

**Expected**

```text
fatigue: elevated_concern
source: assessment:crew-mission-05-assessment
model_output: False

recommendation_type       : review_task_timing
countermeasure_id         : CM-02
priority                  : critical
requires_mission_approval : True
requires_medical_review   : True
warnings[0]               : The recorded fatigue level is 'elevated_concern'; a medical review is flagged for this advisory.
```

**Screen:** Fatigue Alerts / Recommendations → critical severity, medical-review
flag visible, advisory text verbatim.

**Say:** “The `elevated_concern` value is a synthetic fixture input chosen to
exercise the rule. It is not AI model output — `model_output` is false and the
assessment text carries the synthetic marker. The advisory asks for a timing
review and a medical review flag. It gives no diagnosis and no medication
advice.”

**Do not say:** “This crew member is unfit.” “This is a medical emergency.”
“The model predicts…” The model did not produce this value.

---

### Scene 6 — What-if and follow-up lifecycle (`crew-mission-06`)

**Goal:** show a transient schedule edit resolving a conflict, then record the
advisory decision through create → accept → complete, including the approval
gate and terminal-state rejection.

#### 6a. Baseline conflict

```powershell
$c = "crew-mission-06"
$conflicts = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/conflicts?window_start=$ws&window_end=$we"
$recs = Invoke-RestMethod -Method Get -Uri "$base/crew/$c/mission-intel/recommendations?window_start=$ws&window_end=$we"

"conflicts: $($conflicts.conflicts.Count)"
$conflicts.conflicts[0] | Select-Object rule_id, conflict_type, severity, affected_start, affected_end | Format-List
$recs.recommendations[0] | Select-Object recommendation_id, recommendation_type, countermeasure_id, rule_id | Format-List
```

Expected: 1 conflict (`R-RECOVERY-01`, `insufficient_recovery_gap`, `high`,
09:00–09:10) and 1 recommendation (`identify_recovery_opportunity`, `CM-03`).

#### 6b. What-if: insert a 30-minute recovery period

```powershell
$body = @{
  window_start = $ws
  window_end   = $we
  operations   = @(
    @{
      type                  = "add_recovery_period"
      start                 = "2026-11-13T09:00:00Z"
      end                   = "2026-11-13T09:30:00Z"
      shift_following_tasks = $true
    }
  )
} | ConvertTo-Json -Depth 6

$whatif = Invoke-RestMethod -Method Post -Uri "$base/crew/$c/mission-intel/what-if" -ContentType "application/json" -Body $body
$whatif.comparison | Select-Object conflict_count_delta, summary, note | Format-List
"original: $($whatif.comparison.original_metrics.total_conflicts) conflict(s), recovery $($whatif.comparison.original_metrics.total_recovery_minutes) min"
"proposed: $($whatif.comparison.proposed_metrics.total_conflicts) conflict(s), recovery $($whatif.comparison.proposed_metrics.total_recovery_minutes) min"
"resolved: $($whatif.comparison.resolved_conflicts.Count); new: $($whatif.comparison.new_conflicts.Count)"
```

**Expected**

```text
conflict_count_delta : -1
summary  : The proposed schedule has 1 fewer conflicts under the configured rules than the original schedule (1 original, 0 proposed; 1 resolved and 0 new conflict(s)). Free time is 1260 min original vs 1230 min proposed; recovery time is 0 min vs 30 min; the longest recovery gap is 600 min vs 570 min. These are rule-based schedule metrics, not a fatigue prediction.
note     : Fatigue was not re-predicted; this comparison reflects schedule rules only.

original: 1 conflict(s), recovery 0 min
proposed: 0 conflict(s), recovery 30 min
resolved: 1; new: 0
```

**Screen:** What-if Analysis → delta −1, metrics side by side, resolved conflict
card, exact note.

**Say:** “The edit is transient. Nothing is saved. The fatigue value in both
metric objects is copied from the original context; the system does not re-predict
fatigue.”

**Do not say:** “The new schedule improves fatigue.”

#### 6c. Create the follow-up

Use the recommendation id from 6a and the **same window**.

```powershell
$recId = $recs.recommendations[0].recommendation_id

$createBody = @{
  recommendation_id = $recId
  window_start      = $ws
  window_end        = $we
  due_at            = "2026-11-14T12:00:00Z"
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post -Uri "$base/crew/$c/mission-intel/follow-ups" -ContentType "application/json" -Body $createBody
$fuId = $created.follow_up.follow_up_id

$created.follow_up | Select-Object follow_up_id, status, requires_mission_approval, requires_medical_review, due_at | Format-List
$created.data_warnings | Format-List
```

**Expected**

```text
follow_up_id              : fu_<generated>
status                    : suggested
requires_mission_approval : True
requires_medical_review   : False
due_at                    : 2026-11-14T12:00:00Z

code    : follow_up_store_is_process_local
message : Follow-ups are stored in process memory for this phase; they are cleared when the API process restarts. No mission task is changed by a follow-up.
```

**Say:** “This writes only to process memory. The warning is part of the
response, and the UI keeps it visible. No mission task changes.”

#### 6d. Accept

```powershell
$accepted = Invoke-RestMethod -Method Patch -Uri "$base/crew/$c/mission-intel/follow-ups/$fuId" -ContentType "application/json" -Body (@{ action = "accept" } | ConvertTo-Json)
$accepted.follow_up.status
```

Expected: `accepted`.

#### 6e. Complete with approval

```powershell
$completeBody = @{
  action   = "complete"
  approved = $true
  result   = "Demo: mission control reviewed the advisory."
} | ConvertTo-Json

$completed = Invoke-RestMethod -Method Patch -Uri "$base/crew/$c/mission-intel/follow-ups/$fuId" -ContentType "application/json" -Body $completeBody
$completed.follow_up | Select-Object status, approved, result, updated_at | Format-List
```

Expected: `status = completed`, `approved = True`, `result` echoed.

#### 6f. Show that completion is terminal

```powershell
try {
  Invoke-RestMethod -Method Patch -Uri "$base/crew/$c/mission-intel/follow-ups/$fuId" -ContentType "application/json" -Body (@{ action = "complete"; approved = $true } | ConvertTo-Json)
} catch {
  $_.ErrorDetails.Message
}
```

Expected `409`:

```json
{
  "error": {
    "code": "invalid_status_transition",
    "message": "Cannot change follow-up 'fu_<id>' from 'completed' to 'completed'.",
    "details": {
      "follow_up_id": "fu_<id>",
      "current_status": "completed",
      "requested_status": "completed"
    }
  },
  "data_warnings": []
}
```

**Screen:** Follow-ups → status stepper suggested → accepted → completed;
process-local notice visible; repeat action disabled or rejected.

**Say:** “The completion needed explicit approval. Repeating it is rejected by the
state machine. Restarting the API clears these records — that is a documented
Phase 7 limitation, not hidden state.”

---

## 4. Postman walkthrough

Import `backend/app/mission/docs/postman_collection.json`. It uses its own demo
crew (`crew-demo-01`) and seeds it, so it is independent of the six scenario
crews.

Run folders in order:

| Folder | Request | Expected |
| --- | --- | --- |
| 0. Setup | Seed demo crew (normal_routine) | `200/201`, `crew_id = crew-demo-01` |
| 0. Setup | Create night task in the WOCL | `201`, captures `nightTaskId` |
| 1. Read | GET schedule (daily) | `200`, `view=daily`, `data_warnings` array |
| 1. Read | GET overview | `200`, categorical `fatigue_signal.level` |
| 1. Read | GET conflicts | `200`, `rule_set_version`, `conflicts` array |
| 1. Read | GET recommendations | `200`, captures `recommendationId` |
| 2. What-if | POST what-if (move task) | `200`, `comparison.note` exact |
| 3. Follow-ups | POST follow-up (create) | `201`, `suggested`, process-local warning |
| 3. Follow-ups | PATCH follow-up (accept) | `200`, `accepted` |
| 3. Follow-ups | PATCH follow-up (complete, approved) | `200`, `completed` |
| 3. Follow-ups | PATCH follow-up (repeat complete → 409) | `409 invalid_status_transition` |
| 4. Error examples | GET schedule (unknown crew → 404) | `404 crew_not_found` |
| 4. Error examples | POST what-if (bad operation type → 422) | `422 validation_error` |
| 4. Error examples | PATCH follow-up (unknown id → 404) | `404 follow_up_not_found` |

Notes:

- The collection computes a UTC day window in a prerequest script. It will not
  match the fixed Phase 8 fixtures; that is expected. Use PowerShell for the
  scenario story and Postman for contract/error demonstrations.
- Follow-up ids are captured automatically. Running create twice creates two
  records; restart the API to clear them.
- Do not re-run “Seed demo crew” between follow-up steps unless you accept that
  the earlier follow-up records become stale.

---

## 5. Expected screens and outputs by scene

| Scene | Primary screen | Must be visible | Must not be visible |
| --- | --- | --- | --- |
| 1 | Overview | “No conflicts under the configured rules”, warnings area empty | “Safe”, “all clear”, green “healthy” badge |
| 2 | Fatigue Alerts | `monitor`, 3 findings, 3 advisories, no medical flag | Any numeric fatigue score |
| 3 | Conflicts | 4 findings, per-pair `task_ids`, approval flags | “Auto-rebalanced” claim |
| 4 | Mission Calendar | Sleep band 22:00–06:00, task at 23:00, 2 markers | Sleep band treated as a mission-plan input |
| 5 | Recommendations | `critical`, `requires_medical_review=true`, synthetic provenance | Diagnosis, impairment, medication |
| 6 | What-if → Follow-ups | delta −1, exact note, status stepper, process-local warning | “Improved fatigue”, persisted follow-up claim |

---

## 6. Limitations slide (copy-paste)

### Mission Intelligence — limitations

- **Decision support only.** Not a diagnosis, not a fitness-for-duty
  determination, not a treatment plan.
- **No numerical fatigue score.** The only fatigue input is the categorical
  `Assessment.status`; the UI must not synthesize a score.
- **Rule-based comparison.** What-if does not re-predict fatigue; the note is
  fixed: “Fatigue was not re-predicted; this comparison reflects schedule rules
  only.”
- **All times are UTC.** Crew-local time zones and individual circadian phase are
  not modelled.
- **Start-only task loading.** Tasks that start before the window and overlap into
  it are not returned.
- **No task status column.** Every adapted task is `planned`; completed/cancelled
  filtering is not available.
- **Follow-ups are process-local.** They are cleared on API restart and there is
  no `GET /follow-ups` endpoint.
- **Synthetic scenarios.** All six Phase 8 crews are synthetic. Scenario 5’s
  `elevated_concern` is fixture input, not AI model output.
- **Thresholds are configurable assumptions.** No cited source states a numeric
  threshold; every value is centralized in `app/mission/config.py` with an
  evidence label.
- **No real-time push.** The dashboard refreshes on request; there are no
  websockets.
- **Human authority.** Every recommendation requires mission approval, and some
  require medical review. Final authority remains with the crew, mission control,
  and medical staff.

Speaker note: read the first and last bullets, then invite questions. Do not read
all eleven.

---

## 7. Fallback if a live call fails

Use one of these if uvicorn is not running, the database is not seeded, or the
demo machine cannot reach `127.0.0.1:8000`:

1. **Run the end-to-end suite and show the assertions.**
   ```powershell
   & ".\.venv\Scripts\python.exe" -m pytest app/mission/tests/test_scenarios_e2e.py -q
   ```
   Expected: `10 passed`. This proves all six scenarios, the what-if delta, and the
   follow-up lifecycle against the real router mounted in-test.

2. **Show the captured expected JSON** in `06_scenarios.md` §8.2–8.7. Every block
   there is real captured output.

3. **Show the architecture and safety tests.**
   ```powershell
   & ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q
   ```
   Expected: `205 passed, 1 warning`.

Be explicit about which fallback you are using. Do not read JSON as if it were a
live response.

---

## 8. Q&A crib sheet

| Question | Answer |
| --- | --- |
| Is this a diagnosis? | No. It is rule-based decision support. It never diagnoses or measures impairment. |
| Why no fatigue score? | The source model exposes a categorical status only. Inventing a score would be unscientific and against the project rules. |
| Does moving a task improve fatigue? | We do not claim that. We say a change “may reduce risk under rule X”. What-if compares schedule rules only. |
| Why is the crew not “safe” with zero conflicts? | Zero conflicts means these rules, with this data, found nothing. Missing data can mean a rule was skipped; warnings are shown. |
| Why does the same crew have different ids in Postman? | Postman uses `crew-demo-01` and a live window; the scenario demo uses fixed `crew-mission-*` crews and a fixed UTC window. |
| Where do the thresholds come from? | `app/mission/config.py`. Every value is labelled “configurable assumption” because the cited sources state no numeric cut-offs. |
| Is the AI model used? | Person 3’s assessment status is consumed as the fatigue input. The mission layer does not call or rebuild the model. Scenario 5’s value is fixture input, not model output. |
| Why did my follow-up disappear? | Follow-ups are process-local and cleared on restart. This is documented and warned on every response. |
| Can I apply a recommendation? | No. The system records an advisory decision. A human applies any schedule change through the mission process. |
| Why are tasks all “planned”? | `MissionTask` has no status column; `DEFAULT_TASK_STATUS` is `planned`. This is a Person 2 dependency. |
| What happens with no assessment? | Fatigue is `unknown`, `no_assessment_available` is warned, and fatigue-dependent suitability becomes `insufficient_data`. |
| Is the data real NASA data? | No. The six scenarios are synthetic and marked as such. Only the concepts and countermeasure names are sourced from the cited NASA documents. |

---

## 9. Post-demo cleanup

```powershell
# Optional: remove only the six scenario crews.
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --reset

# Stop the API with Ctrl+C in the uvicorn terminal.
```

`--reset` deletes dependent rows and the crew profile only for
`crew-mission-01` … `crew-mission-06`. It does not touch `crew-demo-*` or any
other crew id.
