# Mission Intelligence (`backend/app/mission/`)

Person 4's module for ChronoGuard: rule-based mission-schedule analysis that
turns crew health data and a planned schedule into explainable findings,
advisory countermeasures, transient what-if comparisons, and advisory follow-up
records.

> **Decision support only.** This module does not diagnose, does not measure
> impairment, does not determine fitness for duty, and does not recommend
> medication. It never applies a schedule change. Every recommendation requires
> mission approval, and some require medical review. Final authority remains with
> the crew, mission control, and medical staff.

---

## 1. Status

| Item | State |
| --- | --- |
| Phases 0–9 | Complete |
| Mission tests | `205 passed, 1 warning` |
| Full backend suite | `221 passed, 1 warning` |
| API router | Implemented in `router.py` and registered in `app/routers/__init__.py` |
| Database schema | Unchanged. Reads via `history_service`; no table added |
| Follow-up storage | Process-local, cleared on API restart |
| Commit status | Files are untracked until the owner reviews and commits |

The router is reachable at `/api/v1/crew/{crew_id}/mission-intel/...` through
`app.main:app`. Registration was approved after Phase 9. The end-to-end tests also
mount the router explicitly, so they remain independent of the registry.

---

## 2. What it does

Given a crew id and an explicit UTC window, the module:

1. Reads the crew profile, recent sleep, the latest assessment, and planned tasks
   through `app/services/history_service.py`.
2. Adapts them into immutable transfer objects (`AstronautContext`).
3. Runs pure schedule, suitability, and conflict rules.
4. Generates at most five non-pharmacological advisory countermeasures.
5. Optionally evaluates a transient schedule edit (what-if) without saving it.
6. Records advisory follow-up decisions in process memory.

### Rules implemented

| Family | Rule ids | Meaning |
| --- | --- | --- |
| Data availability | `R-DATA-01`, `R-FATIGUE-DATA-01`, sleep-data warnings | Required input missing: no judgement, never “probably fine”. |
| Task suitability | `R-FATIGUE-01..04`, `R-SLEEP-01..03`, `R-OK-01` | Categorical fatigue, last-sleep shortfall, and sleep-window overlap. |
| Conflict detection | `R-SLEEP-WINDOW-01`, `R-RECOVERY-01`, `R-RECOVERY-02`, `R-FATIGUE-CRITICAL-01`, `R-WORKLOAD-01`, `R-CIRCADIAN-01` | Schedule conflicts with explanations and config keys. |
| What-if | Reuses the conflict rules | Rule-based comparison only; fatigue is copied, not re-predicted. |

Rule details live in `docs/03_integration.md`, `docs/04_conflict_rules.md`, and
`docs/05_recommendations.md`.

### What it explicitly does not do

- No numeric fatigue score. The only fatigue input is the categorical
  `Assessment.status`.
- No diagnosis, no impairment prediction, no medication or treatment advice.
- No schedule write, no task approval, no auto-apply.
- No machine-learning model training or inference. Person 3's assessment is
  consumed as an input.
- No database schema change and no write to mission tables.
- No crew-local time zone or individual circadian phase. All clock logic is UTC.

---

## 3. Architecture

```mermaid
flowchart LR
    DB[(Existing SQLite tables)] --> HS[app/services/history_service.py]
    HS --> AD[adapters.py]
    AD --> CTX[AstronautContext]
    CTX --> SCHED[schedule.py]
    CTX --> SUIT[integration.py]
    CTX --> CONF[conflicts.py]
    CONF --> REC[recommendations.py]
    CTX --> WHAT[scenarios.py]
    WHAT --> CONF
    SCHED --> API[router.py]
    SUIT --> API
    CONF --> API
    REC --> API
    WHAT --> API
    API --> HTTP[/api/v1/crew/:id/mission-intel]
    API --> FU[followups.py<br/>process memory]
    CONF --> WARN[data_warnings]
    API --> WARN
```

### Module map

| File | Responsibility |
| --- | --- |
| `config.py` | Frozen `MissionConfig` with every threshold and its evidence label. |
| `models.py` | Pydantic v2 transfer objects, enums, UTC validation. No DB models. |
| `adapters.py` | Read-only DB → DTO mapping via `history_service`; context building; warnings. |
| `schedule.py` | Pure daily/weekly windows, free gaps, overlap helpers. |
| `integration.py` | Pure task-suitability rules (`R-FATIGUE-*`, `R-SLEEP-*`, `R-OK-01`). |
| `conflicts.py` | Pure conflict rules and `DataWarning`s. |
| `recommendations.py` | Conflict → advisory countermeasure (`CM-01`…`CM-07`), capped at 5. |
| `scenarios.py` | Five transient schedule operations and rule-based comparison. |
| `scenario_fixtures.py` | Six deterministic synthetic scenarios; idempotent seed/reset CLI. |
| `api_models.py` | HTTP request/response envelopes, operation union, enums. |
| `errors.py` | Mission exceptions, consistent error body, `MissionRoute`. |
| `followups.py` | Lock-protected process-local follow-up store and state machine. |
| `task_checks.py` | Non-blocking candidate-task check used by the `mission_service` hook. |
| `router.py` | Seven endpoints under `/crew/{crew_id}/mission-intel`. |
| `tests/` | Unit, API, task-check, and end-to-end scenario tests. |
| `docs/` | Phase 0–9 documentation and the Postman collection. |

### Design rules followed

- **Pure core.** `schedule.py`, `integration.py`, `conflicts.py`,
  `recommendations.py`, and `scenarios.py` do no I/O. They take DTOs and return
  DTOs, which makes them deterministic and easy to test.
- **One read path.** `adapters.py` is the only place that touches the database,
  and it goes through `history_service`.
- **No schema change.** Follow-ups are in memory because the existing
  `ActionHistory` table cannot store the recommendation/rule linkage.
- **Stable HTTP shape.** Every response, including errors, has a top-level
  `data_warnings` array and a stable `error` object.
- **Deterministic ids.** Conflict and recommendation ids are hashes of their
  inputs; repeating a request returns the same ids.

---

## 4. Quick start

Run from `backend/` in Windows PowerShell.

```powershell
# 1. Install/sync dependencies if needed.
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

# 2. Run the mission test suite.
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q

# 3. Seed the six deterministic scenarios (idempotent).
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures

# 4. Recreate them from scratch (only crew-mission-* rows are touched).
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --reset

# 5. Start the API.
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
```

Expected test result: `205 passed, 1 warning`. The only warning is the
pre-existing Starlette `TestClient` deprecation.

### Calling the API

The routes are registered and available while the API is running:

```powershell
$base = "http://127.0.0.1:8000/api/v1"
$ws = "2026-11-13T00:00:00Z"
$we = "2026-11-14T00:00:00Z"

Invoke-RestMethod -Method Get -Uri "$base/crew/crew-mission-02/mission-intel/conflicts?window_start=$ws&window_end=$we" | ConvertTo-Json -Depth 12
```

A plain `{"detail":"Not Found"}` means the running server predates the
registration or the router is not mounted. A `crew_not_found` envelope proves the
mission router is active.

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/crew/{crew_id}/mission-intel/schedule` | Daily/weekly schedule + sleep bands |
| `GET` | `/crew/{crew_id}/mission-intel/overview` | Health, task suitability, counts |
| `GET` | `/crew/{crew_id}/mission-intel/conflicts` | Rule findings |
| `GET` | `/crew/{crew_id}/mission-intel/recommendations` | Advisory countermeasures |
| `POST` | `/crew/{crew_id}/mission-intel/what-if` | Transient rule-based comparison |
| `POST` | `/crew/{crew_id}/mission-intel/follow-ups` | Create advisory follow-up |
| `PATCH` | `/crew/{crew_id}/mission-intel/follow-ups/{follow_up_id}` | Accept/skip/complete |

Full request/response contracts, error codes, and warning codes:
`docs/05_api_contracts.md`.

---

## 5. Configuration

Every value lives in `app/mission/config.py` and is frozen at import time. Per
project rules:

- No cited source in `docs/01_references.md` states a numeric threshold.
- Therefore **every numeric value below is a `configurable assumption`**, even
  where the underlying concept is evidence-based (`source: docs/01_references.md`).
- The three source ids are `NASA-HRP-Sleep-Risk`,
  `NASA-TM-Fatigue-Countermeasures`, and `NASA-STD-3001-Vol2`.

`DEFAULT_CONFIG` is used by the API. Tests may pass an explicit `MissionConfig`,
but rules never mutate the default.

### 5.1 Sleep opportunity and circadian placement

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `MIN_SLEEP_WINDOW_MINUTES` | `420` | Minimum preserved sleep opportunity. | Reserved; not read by current rules |
| `PROTECTED_SLEEP_WINDOW_START_HOUR` | `22` | Fallback protected sleep window start (UTC). | Conflicts, recommendations |
| `PROTECTED_SLEEP_WINDOW_END_HOUR` | `7` | Fallback protected sleep window end (UTC); may cross midnight. | Conflicts, recommendations |
| `WOCL_START_HOUR` | `2` | Window of Circadian Low start (UTC). | Conflicts, recommendations |
| `WOCL_END_HOUR` | `6` | Window of Circadian Low end (UTC). | Conflicts, recommendations |
| `WOCL_TOLERANCE_MINUTES` | `30` | Buffer around the WOCL. | Conflicts, recommendations |

### 5.2 Recovery and workload

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `MIN_RECOVERY_GAP_MINUTES` | `30` | Required gap between two demanding tasks. | Conflicts, recommendations, what-if metrics |
| `WORKLOAD_WINDOW_HOURS` | `24` | Rolling window for demanding-task counts. | Conflicts, what-if metrics |
| `MAX_DEMANDING_TASKS_PER_WINDOW` | `3` | Demanding tasks allowed per workload window. | Conflicts, recommendations, metrics |
| `MAX_DEMANDING_TASK_HOURS_PER_WINDOW` | `480` | Cumulative demanding minutes per workload window. | Conflicts, recommendations, metrics |
| `DEMANDING_WORKLOAD_LEVELS` | `("high",)` | Workload levels treated as demanding. | Adapters, conflicts, suitability, metrics |

### 5.3 Alertness and task mapping

These fill fields the database does not store. They are display/rule
conventions, not NASA instruments.

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `ALERTNESS_BY_WORKLOAD` | `low=2, medium=3, high=5` | Maps workload to required alertness (1–5). | Adapters |
| `CRITICAL_ALERTNESS_BONUS` | `1` | Bonus applied before the cap. | Adapters |
| `CRITICAL_TASK_ALERTNESS_REQUIREMENT` | `4` | Minimum alertness for a critical task. | Adapters, conflicts, suitability, metrics |
| `MIN_ALERTNESS` | `1` | Scale lower bound. | Adapters, models |
| `MAX_ALERTNESS` | `5` | Scale upper bound. | Adapters, models |
| `PRIORITY_BY_WORKLOAD` | `low→low, medium→medium, high→high` | Derived display priority. | Adapters, task checks |
| `CRITICAL_PRIORITY` | `critical` | Priority for `is_critical=True`. | Adapters, task checks |
| `DEFAULT_TASK_STATUS` | `planned` | Status for every adapted task (no DB column). | Adapters |

### 5.4 Conflict detection

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `CONFLICT_OVERLAP_TOLERANCE_MINUTES` | `0` | Overlap tolerance for windows. | Conflicts, what-if metrics |
| `PLANNING_HORIZON_HOURS` | `72` | Default look-ahead when no window is supplied. | API models, recommendations, router, task checks |
| `MAX_CONTEXT_TASKS` | `100` | Cap on tasks loaded into one context. | Adapters |

### 5.5 Schedule and suitability

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `MIN_FREE_GAP_MINUTES` | `15` | Shortest interval reported as a free gap. | Schedule |
| `SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO` | `0.75` | Severe shortfall vs. sleep target. | Suitability |
| `SLEEP_SHORTFALL_REVIEW_RATIO` | `0.90` | Review threshold vs. sleep target. | Suitability, conflicts, metrics |

### 5.6 Sleep history and inference

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `RECENT_SLEEP_LOOKBACK_DAYS` | `14` | Days of recent sleep loaded. | Adapters |
| `RECENT_SLEEP_MAX_RECORDS` | `14` | Max recent sleep records kept. | Adapters |
| `HABITUAL_SLEEP_LOOKBACK_DAYS` | `14` | Days used to infer the habitual window. | Adapters |
| `HABITUAL_SLEEP_MIN_RECORDS` | `3` | Minimum consistent records before inference. | Adapters, conflicts |
| `HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES` | `90` | Circular distance allowed from mean sleep times. | Adapters, conflicts |
| `SLEEP_DEBT_LOOKBACK_DAYS` | `7` | Lookback for a sleep-debt proxy. | Reserved; not read by current rules |
| `SLEEP_DEBT_THRESHOLD_MINUTES` | `300` | Deficit that would raise a debt indicator. | Reserved; not read by current rules |
| `INSUFFICIENT_DATA_MIN_DAYS` | `3` | Minimum usable history for indicators. | Reserved; not read by current rules |

### 5.7 Recommendations and reserved risk indicator

| Key | Default | What it controls | Used by |
| --- | --- | --- | --- |
| `MIN_STRUCTURED_BREAK_MINUTES` | `15` | Minimum suggested recovery break. | Recommendations |
| `MAX_RECOMMENDATIONS_PER_RESPONSE` | `5` | Output cap per evaluation. | Recommendations |
| `RISK_WEIGHT_SLEEP` | `1.0` | Weight in a future combined indicator. | Reserved; not read by current rules |
| `RISK_WEIGHT_CIRCADIAN` | `1.0` | Weight in a future combined indicator. | Reserved; not read by current rules |
| `RISK_WEIGHT_WORKLOAD` | `1.0` | Weight in a future combined indicator. | Reserved; not read by current rules |
| `RISK_FLAG_THRESHOLD` | `1.0` | Future advisory-flag threshold. | Reserved; not read by current rules |
| `NAP_MIN_MINUTES` | `10` | Lower bound for a future strategic nap suggestion. | Reserved; not read by current rules |
| `NAP_MAX_MINUTES` | `30` | Upper bound for a future strategic nap suggestion. | Reserved; not read by current rules |

### 5.8 Validation

`MissionConfig` rejects combinations that make rules ambiguous:

- equal WOCL start/end,
- equal protected-sleep start/end,
- `MIN_ALERTNESS >= MAX_ALERTNESS`,
- alertness values outside the scale,
- missing workload keys in the alertness or priority maps,
- `NAP_MIN_MINUTES > NAP_MAX_MINUTES`.

---

## 6. Assumptions that must be stated in any demo or report

1. **All thresholds are configurable assumptions.** The cited NASA sources
   describe risks and countermeasures but state no numeric cut-offs.
2. **Fatigue is categorical.** `Assessment.status` is mapped to `unknown`,
   `no_flag`, `monitor`, or `elevated_concern`. No numeric score is invented or
   read.
3. **UTC only.** Clock placement rules assume UTC. Individual circadian phase and
   crew-local time are not modelled.
4. **Task fields are partly derived.** The database has no priority, required
   alertness, or status columns; these come from `config.py` mapping.
5. **Tasks are start-only in a window.** A task that starts before the window and
   overlaps into it is not returned by `get_upcoming_tasks`.
6. **Sleep windows are inferred.** `planned_sleep_windows` requires at least
   `HABITUAL_SLEEP_MIN_RECORDS` consistent records; it is not a mission-planning
   input.
7. **What-if is not a fatigue model.** It re-runs schedule rules. `fatigue_level`
   in both metric sets is copied from the original context.
8. **Follow-ups are advisory bookkeeping.** They do not change a task and are
   cleared when the API process restarts.
9. **Scenario data is synthetic.** Six `crew-mission-*` fixtures are marked as
   simulated. Scenario 5's `elevated_concern` is fixture input, not model output.
10. **Recommendations are non-pharmacological only.** `CM-01`…`CM-07` cover
    sleep scheduling, timing, recovery, workload redistribution, lighting,
    strategic napping, and monitoring. No medication is mentioned.

---

## 7. Dependencies on other members

The module works today without any other member changing code. Each dependency
below has a documented fallback. Full details and exact field requests:
`docs/05_api_contracts.md` §10 (Person 2) and §11 (Person 3).

### Person 2 — data and API

| Need | Current fallback | Impact |
| --- | --- | --- |
| Task-overlap query (`get_tasks_overlapping`) | Start-only loading | Tasks already running when a window opens are invisible |
| `MissionTask.status` | `DEFAULT_TASK_STATUS = planned` | Completed/cancelled tasks keep driving conflicts |
| Persistent follow-up linkage | Process-local store | Records lost on restart; no `GET /follow-ups` |
| `MissionTask.priority` | Derived from workload + `is_critical` | Display and rules use derived values |
| `MissionTask.required_alertness` | Derived from workload + criticality | Same |
| Task categories `sleep`, `communication`, `rest_recovery` | Sleep inferred; recovery only in what-if | No planned sleep/recovery blocks |
| Crew clock/sleep-phase reference | UTC clock assumptions | Circadian placement is UTC-only |
| `MissionTask.notes` returned by the API | Stored but not returned | Reviewers cannot see notes |
| `Countermeasure` catalogue seed/read | Fixed table in `recommendations.py` | UI gets id + name from the advisory |

### Person 3 — assessment

| Need | Current fallback | Impact |
| --- | --- | --- |
| Stable `Assessment.status` values | Unknown values map to `unknown` | Safe, but a new status loses granularity |
| Structured `contributing_factors` | Passed through verbatim | UI renders raw JSON |
| Numeric score with documented scale | Not read | Deliberate: no invented score |
| `Assessment.valid_until` / freshness | Latest row used; id exposed in `source` | A stale assessment is not flagged |

### Integration edits outside this folder

1. **Applied:** `mission_router` is registered in
   `backend/app/routers/__init__.py` (approved after Phase 9).
2. **Applied:** `log_task_warnings(...)` is called in
   `backend/app/services/mission_service.py` after `commit()` in `create_task`
   and `update_task` (approved after Phase 9). The helper only logs and never
   blocks a write. See `docs/05_api_contracts.md` §12.2.

---

## 8. Testing

```powershell
# Mission module only.
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q

# End-to-end scenarios only (six scenarios, what-if, follow-up lifecycle).
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests/test_scenarios_e2e.py -q

# Full backend suite.
& ".\.venv\Scripts\python.exe" -m pytest -q
```

Expected at the time of writing:

| Command | Result |
| --- | --- |
| Mission module | `205 passed, 1 warning` |
| `test_scenarios_e2e.py` | `10 passed` |
| Full backend | Green; run it to confirm the current count |

The mission tests use their own isolated in-memory SQLite engine and never touch
a real database file. `tests/conftest.py` provides `engine`, `session`,
`session_factory`, and a `client` that mounts the mission router manually.

Test coverage includes:

- UTC validation and naive-datetime rejection,
- every conflict rule and every warning path,
- suitability statuses and reasons,
- recommendation wording bans (no “improves”, no medication terms),
- deterministic ids,
- the shared error envelope and every error code,
- the what-if operation set and semantic failures,
- the follow-up state machine, approval gate, and process-local warning,
- all six Phase 8 scenarios end to end.

### Manual API testing

- **Postman:** import `docs/postman_collection.json`. It seeds its own
  `crew-demo-01` and runs read, what-if, follow-up, and error examples in order.
- **PowerShell:** see `docs/09_final_demo.md` for exact commands and expected
  output for the six scenario crews.
- **Router registration:** required for either; see §1.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'app'` | Script run outside `backend/` without `PYTHONPATH` | Run from `backend/` or set `$env:PYTHONPATH` to the backend path. |
| `{"detail":"Not Found"}` on a mission route | Running server predates registration, or the router is not mounted | Restart uvicorn; confirm the registration line in `app/routers/__init__.py`. |
| `404 crew_not_found` | Unknown crew id | Seed scenarios or use an existing crew. |
| `422 validation_error` on a window | Naive, reversed, or malformed datetime | Send RFC 3339 with `Z`/offset and `end > start`. |
| Conflicts are empty but warnings are not | A rule was skipped or input is missing | Show the warning; do not treat as “safe”. |
| A task overlapping the window is missing | Start-only loading limitation | Documented Person 2 dependency; do not patch the UI around it. |
| Follow-up disappeared | API restarted; store is process-local | Recreate it; the warning says so. |
| `404 recommendation_not_found` | Different window or changed data | Use the same window that produced the recommendation. |
| `409 invalid_status_transition` | Repeating or invalid action | Refresh the record; `skipped`/`completed` are terminal. |
| `422 mission_approval_required` | Completing without approval | Confirm with the reviewer, then send `approved: true`. |
| Seed says “skipped” | Crew already exists | Add `--reset` to recreate that scenario. |

---

## 10. Documentation index

| Document | Contents |
| --- | --- |
| `docs/00_repo_findings.md` | Repository survey and constraints. |
| `docs/01_references.md` | Sole source of truth for scientific claims. |
| `docs/02_requirements.md` | Requirements, rule concepts, countermeasure catalogue. |
| `docs/03_integration.md` | Data adaptation, schedule helpers, suitability rules. |
| `docs/04_conflict_rules.md` | Six conflict rules, severity, data warnings. |
| `docs/05_recommendations.md` | Countermeasure mapping and advisory wording. |
| `docs/05_api_contracts.md` | Authoritative HTTP contract, errors, warnings, Person 2/3 needs, integration status. |
| `docs/06_scenarios.md` | What-if design and six Phase 8 scenarios with captured output. |
| `docs/07_ux_spec.md` | Eight-screen UX/UI spec, states, wording, accessibility. |
| `docs/08_dashboard_data_requirements.md` | Person 1 endpoint/field/refresh/error guide with exact payloads. |
| `docs/09_final_demo.md` | Run-of-show, PowerShell/Postman steps, limitations slide. |
| `docs/postman_collection.json` | Runnable Postman collection. |

---

## 11. Safety and contribution rules

- Stay inside `backend/app/mission/` unless the owner approves an integration
  edit (the router registration and the `mission_service.py` warning hook are
  applied).
- Do not change another member's models, schemas, routers, or services.
- Add every new threshold to `config.py` with an evidence label before using it.
- Never invent a NASA finding, statistic, dataset, API field, or model output.
- Keep all wording advisory: “consider”, “review”, “may reduce risk under rule
  X”. Never “improves fatigue”, “prevents”, “diagnoses”, or “medication”.
- Add tests first for any contract change, then update `05_api_contracts.md`, the
  UX spec, and the dashboard requirements.
- Run the mission suite after every change and report changed files before
  moving on.
