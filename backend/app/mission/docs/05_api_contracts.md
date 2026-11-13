# Phase 7 — Mission Intelligence API Contracts

Status: implementation and tests complete for Phase 7. All mission code lives under
`backend/app/mission/`. The router registration in
[Section 12.1](#121-router-registration-applied) and the `mission_service.py`
hook in
[Section 12.2](#122-non-blocking-warnings-in-mission_servicepy-applied) were
approved and applied after Phase 9.

Files in this phase:

- `app/mission/router.py` — the seven endpoints.
- `app/mission/api_models.py` — Pydantic request/response envelopes.
- `app/mission/errors.py` — mission exceptions and the consistent error body.
- `app/mission/followups.py` — process-local follow-up store and transitions.
- `app/mission/task_checks.py` — non-blocking candidate-task check for the
  proposed `mission_service` integration.
- `app/mission/adapters.py` — `_required_alertness` exposed as public
  `required_alertness` for reuse.
- `app/mission/tests/test_api.py` — endpoint, error, warning, and lifecycle
  tests.
- `app/mission/tests/test_task_checks.py` — non-blocking helper tests.
- `app/mission/tests/conftest.py` — added `session_factory` and `client`
  fixtures.
- `app/mission/docs/postman_collection.json` — runnable collection.
- `app/mission/docs/05_api_contracts.md` — this document.

Nothing here diagnoses, predicts impairment, or recommends medication. Every
suggestion is review-oriented and final authority remains with the crew, mission
control, and medical staff.

---

## 1. Mount point and conventions

The router is registered in `app/routers/__init__.py` and mounted by the
application factory under `/api/v1`. Every route is:

```
/api/v1/crew/{crew_id}/mission-intel/...
```

Conventions used by every endpoint:

| Topic | Contract |
| --- | --- |
| Datetimes | RFC 3339 with an explicit offset. `Z` is accepted. Naive values are rejected with `422`. Internally everything is UTC. |
| Unknown crew | `404` with `error.code = "crew_not_found"`. |
| Semantic validation | `422` with `error.code = "validation_error"` (reversed window, naive datetime, unknown task id, impossible operation, bad follow-up transition body). |
| Pydantic validation | `422` with `error.code = "validation_error"` and one `details` entry per field. |
| Warnings | Every response, including errors, contains a top-level `data_warnings` array. |
| Writes | Only follow-ups are written, and only to process memory. No mission task, assessment, or check-in is created or changed by this router. |
| Determinism | Conflict and recommendation ids are deterministic hashes of the inputs. Repeating the same request returns the same ids. |

## 2. Common response shapes

### 2.1 Success envelope

Every successful response contains `data_warnings` at the top level. Each
warning has the shape:

```json
{
  "code": "no_assessment_available",
  "message": "No Assessment row is available for this crew member, so the fatigue level is 'unknown'.",
  "rule_id": null,
  "task_id": null
}
```

### 2.2 Error envelope

Errors use a single stable body. `details` is `null`, an object, or a list,
depending on the error.

```json
{
  "error": {
    "code": "crew_not_found",
    "message": "Crew member 'crew-missing' was not found.",
    "details": { "crew_id": "crew-missing" }
  },
  "data_warnings": []
}
```

### 2.3 Error codes

| HTTP | `error.code` | Raised when |
| --- | --- | --- |
| 404 | `crew_not_found` | The crew id does not exist. |
| 404 | `recommendation_not_found` | The recommendation id is not produced by the current evaluation of the supplied window. |
| 404 | `follow_up_not_found` | The follow-up id is unknown or belongs to another crew. |
| 409 | `invalid_status_transition` | Accepting/skipping/completing from a state that does not allow it. |
| 422 | `mission_approval_required` | Completing a follow-up that requires mission approval without `approved=true`. |
| 422 | `validation_error` | Request validation failed, or a semantic rule rejected the request (reversed/naive window, unknown task, impossible operation, bad body). |

### 2.4 Data warning codes

| `code` | Meaning |
| --- | --- |
| `no_assessment_available` | No `Assessment` row exists, so fatigue is `unknown`. |
| `assessment_insufficient_data` | The latest assessment reports `insufficient_data`, so fatigue is `unknown`. |
| `no_recent_sleep` | No recent valid `SleepRecord`; sleep-shortfall rules and sleep history were not evaluated. |
| `no_planned_sleep_window` | No habitual sleep window could be inferred; sleep-window rules were skipped and the circadian rule used the configured fallback. |
| `no_tasks_in_window` | The requested window contains no task that starts inside it. |
| `conflict_data_warning` | A Phase 4 rule could not be evaluated. `rule_id` names the rule. |
| `follow_up_store_is_process_local` | Present on every follow-up create/patch response. See [Section 9](#9-follow-up-storage-limitation). |

Warnings never replace an error and never mean "safe". `insufficient_data` is
reported explicitly instead of falling back to a "probably fine" answer.

---

## 3. `GET /crew/{crew_id}/mission-intel/schedule`

Return one daily or weekly schedule for one crew member.

### Query parameters

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `view` | `daily` or `weekly` | `daily` | A week is seven days starting at the requested date's UTC midnight; it is not forced to Monday. |
| `date` | ISO date | today in UTC | `YYYY-MM-DD`. |

### Response `200`

```json
{
  "crew_id": "crew-demo-01",
  "view": "daily",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "tasks": [
    {
      "task_id": "task-wake",
      "astronaut_id": "crew-demo-01",
      "name": "Night wake",
      "category": "maintenance",
      "start_time": "2026-11-13T03:00:00Z",
      "end_time": "2026-11-13T04:00:00Z",
      "priority": "high",
      "workload_level": "high",
      "required_alertness": 5,
      "status": "planned",
      "is_critical": false,
      "duration_minutes": 60
    }
  ],
  "planned_sleep_windows": [
    {
      "start_time": "2026-11-13T22:00:00Z",
      "end_time": "2026-11-14T06:00:00Z",
      "source": "inferred_habitual_sleep",
      "duration_minutes": 480
    }
  ],
  "data_warnings": []
}
```

Notes:

- Only tasks that **start** inside the window are loaded. A task that starts
  before the window and overlaps into it is not returned; this is the inherited
  `get_upcoming_tasks` limitation described in
  [Section 10](#10-person-2-databaseapi-needs).
- `planned_sleep_windows` is inferred from at least three consistent sleep
  records. It is not a mission-planning input yet.

### Errors

| Case | Result |
| --- | --- |
| Unknown crew | `404 crew_not_found` |
| `view` not in `daily`/`weekly` | `422 validation_error` |
| Malformed `date` | `422 validation_error` |

---

## 4. `GET /crew/{crew_id}/mission-intel/overview`

Combined health, upcoming-task suitability, and advisory counts.

### Query parameters

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `window_start` | datetime | now (UTC) | Must be supplied with `window_end`. |
| `window_end` | datetime | now + 72 h | Must be supplied with `window_start`. |

`PLANNING_HORIZON_HOURS = 72` is a **configurable assumption** in
`app/mission/config.py`.

### Response `200` (abridged)

```json
{
  "crew": {
    "crew_id": "crew-demo-01",
    "display_name": "Luna Park",
    "role": "Flight Engineer",
    "sleep_target_hours": 8.0
  },
  "health": {
    "fatigue_signal": {
      "level": "elevated_concern",
      "source": "assessment:assessment-demo",
      "contributing_factors": [{ "factor": "synthetic_test_input" }]
    },
    "latest_sleep": {
      "sleep_id": "sleep-demo-2",
      "start_time": "2026-11-12T22:00:00Z",
      "end_time": "2026-11-13T06:00:00Z",
      "interruptions": 0,
      "quality": "valid",
      "duration_minutes": 480
    },
    "recent_sleep": [],
    "planned_sleep_windows": []
  },
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "upcoming_tasks": [
    {
      "task": {
        "task_id": "task-wake",
        "astronaut_id": "crew-demo-01",
        "name": "Night wake",
        "category": "maintenance",
        "start_time": "2026-11-13T03:00:00Z",
        "end_time": "2026-11-13T04:00:00Z",
        "priority": "high",
        "workload_level": "high",
        "required_alertness": 5,
        "status": "planned",
        "is_critical": false,
        "duration_minutes": 60
      },
      "suitability": {
        "task_id": "task-wake",
        "astronaut_id": "crew-demo-01",
        "status": "not_recommended",
        "reasons": [
          "R-FATIGUE-01: Fatigue level 'elevated_concern' combined with a demanding task is not recommended."
        ],
        "rule_ids": ["R-FATIGUE-01"],
        "inputs_used": {
          "fatigue_level": "elevated_concern",
          "last_sleep_minutes": 480,
          "sleep_target_minutes": 480,
          "sleep_ratio": 1.0,
          "required_alertness": 5,
          "priority": "high",
          "workload_level": "high",
          "is_critical": false,
          "demanding": true,
          "overlaps_planned_sleep": false,
          "protected_sleep_task": false,
          "thresholds": {
            "SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO": 0.75,
            "SLEEP_SHORTFALL_REVIEW_RATIO": 0.9,
            "CRITICAL_TASK_ALERTNESS_REQUIREMENT": 4,
            "DEMANDING_WORKLOAD_LEVELS": ["high"]
          }
        }
      }
    }
  ],
  "conflict_count": 2,
  "recommendation_count": 2,
  "data_warnings": []
}
```

Notes:

- There is intentionally no numeric fatigue score. `fatigue_signal.level` is the
  only fatigue input, and it is the categorical `Assessment.status`.
- Suitability status is one of `suitable`, `review`, `not_recommended`, or
  `insufficient_data`.
- A crew with no assessment gets `no_assessment_available` and `unknown`
  fatigue; suitability that needs fatigue becomes `insufficient_data`.

---

## 5. `GET /crew/{crew_id}/mission-intel/conflicts`

Rule-based conflict report for one crew and one window.

### Query parameters

Same `window_start` / `window_end` pair as the overview; defaults to the 72-hour
planning horizon.

### Response `200` (one conflict shown)

```json
{
  "crew_id": "crew-demo-01",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {
      "conflict_id": "cf_d352722bf6c9c1fd",
      "rule_id": "R-CIRCADIAN-01",
      "conflict_type": "circadian_low_alertness",
      "severity": "high",
      "astronaut_id": "crew-demo-01",
      "task_ids": ["task-wake"],
      "affected_start": "2026-11-13T03:00:00Z",
      "affected_end": "2026-11-13T04:00:00Z",
      "explanation": "Rule R-CIRCADIAN-01: task 'task-wake' (Night wake) has clock placement 03:00-04:00 UTC, which is inside the configurable WOCL 02:00-06:00 UTC with 30 min tolerance.",
      "suggested_action": "Review task timing under rule R-CIRCADIAN-01; scheduling high-alertness work outside the circadian trough may reduce risk. Advisory only; mission approval is required.",
      "source_ids": ["NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"],
      "config_keys": ["WOCL_START_HOUR", "WOCL_END_HOUR", "WOCL_TOLERANCE_MINUTES"],
      "task_id": "task-wake"
    }
  ],
  "config_keys": ["WOCL_START_HOUR", "WOCL_END_HOUR", "WOCL_TOLERANCE_MINUTES"],
  "data_warnings": []
}
```

Notes:

- Conflicts are ordered by `affected_start`, then severity (highest first), then
  `conflict_id`.
- `task_id` is a convenience field equal to the first entry of `task_ids`.
- Every `explanation` and `suggested_action` is review-oriented. The word
  "improves" and any medication term are banned by tests.

---

## 6. `GET /crew/{crew_id}/mission-intel/recommendations`

Advisory recommendations derived from the conflict report. The generator returns
at most `MAX_RECOMMENDATIONS_PER_RESPONSE = 5` items (configurable assumption).

### Response `200` (one recommendation shown)

```json
{
  "crew_id": "crew-demo-01",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "conflict_count": 2,
  "recommendations": [
    {
      "recommendation_id": "rc_9c36a4fae6115c14",
      "recommendation_type": "review_task_timing",
      "related_conflict_id": "cf_05469e92ad39bb99",
      "astronaut_id": "crew-demo-01",
      "countermeasure_id": "CM-02",
      "countermeasure_name": "Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough",
      "rule_id": "R-FATIGUE-CRITICAL-01",
      "reason": "Rule R-FATIGUE-CRITICAL-01 reports fatigue level 'elevated_concern' before task 'task-wake'.",
      "suggested_action": "Consider moving the critical task to a different schedule window or inserting a recovery opportunity before it. Review under rule R-FATIGUE-CRITICAL-01; this may reduce risk under rule R-FATIGUE-CRITICAL-01.",
      "expected_benefit": "Removes the co-occurrence of an 'elevated_concern' fatigue signal with a critical task under rule R-FATIGUE-CRITICAL-01; no physiological effect is claimed.",
      "priority": "critical",
      "explanation": "The fatigue input is a categorical assessment signal, not a measurement of impairment.",
      "source_ids": ["NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"],
      "preconditions": ["Mission planner and, when flagged, medical staff review the task timing."],
      "warnings": ["The recorded fatigue level is 'elevated_concern'; a medical review is flagged for this advisory."],
      "requires_mission_approval": true,
      "requires_medical_review": true,
      "advisory_text": "Consider moving the critical task to a different schedule window or inserting a recovery opportunity before it. ... This is advisory decision support only; decisions remain with the crew, mission control, and medical staff."
    }
  ],
  "data_warnings": []
}
```

Notes:

- `recommendation_id` is deterministic for the same crew, window, tasks, sleep,
  and fatigue signal. A follow-up should use the **same window** that produced
  the recommendation.
- `requires_mission_approval` is always `true`.
- `requires_medical_review` is `true` only when the recommendation depends on the
  highest categorical fatigue level, `elevated_concern`.
- Conflict types with no safe advisory (missing data) produce no recommendation.

---

## 7. `POST /crew/{crew_id}/mission-intel/what-if`

Compare a transient schedule edit with the original schedule. Nothing is
persisted and the original context is never mutated.

### Request body

```json
{
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "operations": [
    {
      "type": "move_task",
      "task_id": "task-wake",
      "new_start": "2026-11-13T12:00:00Z"
    }
  ]
}
```

The base window is used to build the original context and as the comparison's
evaluation window. Operations are applied in order. `operations` must contain
between 1 and 20 items.

### Operation types

| `type` | Fields | Meaning |
| --- | --- | --- |
| `delay_task` | `task_id`, `minutes` (`> 0`) | Shift one task later by whole minutes. |
| `move_task` | `task_id`, `new_start` | Move one task to a new start, preserving duration. |
| `add_recovery_period` | `start`, `end`, `shift_following_tasks` (default `true`), optional `task_id`, optional `name` | Insert a `rest_recovery` block. By default later open tasks are pushed forward. |
| `redistribute_workload` | `task_id`, `new_start` | Move one demanding task to a different slot. Rejects non-demanding tasks. |
| `modify_sleep_window` | `new_start`, `new_end`, `window_index` (default `0`) | Replace one planned/inferred sleep window. |

### Response `200` (abridged)

```json
{
  "crew_id": "crew-demo-01",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "applied_operations": [
    { "index": 0, "type": "move_task", "task_id": "task-wake" }
  ],
  "comparison": {
    "original_metrics": {
      "evaluation_start": "2026-11-13T00:00:00Z",
      "evaluation_end": "2026-11-14T00:00:00Z",
      "conflicts_by_type": [],
      "total_conflicts": 2,
      "highest_severity": "critical",
      "workload_windows": [],
      "total_free_minutes": 1320,
      "total_recovery_minutes": 0,
      "total_recovery_and_free_minutes": 1320,
      "longest_recovery_gap_minutes": 780,
      "tasks_inside_sleep_windows": 0,
      "task_ids_inside_sleep_windows": [],
      "fatigue_level": "elevated_concern",
      "fatigue_source": "assessment:assessment-demo",
      "data_warning_count": 0,
      "data_warning_rule_ids": []
    },
    "proposed_metrics": {
      "evaluation_start": "2026-11-13T00:00:00Z",
      "evaluation_end": "2026-11-14T00:00:00Z",
      "conflicts_by_type": [],
      "total_conflicts": 1,
      "highest_severity": "critical",
      "workload_windows": [],
      "total_free_minutes": 1320,
      "total_recovery_minutes": 0,
      "total_recovery_and_free_minutes": 1320,
      "longest_recovery_gap_minutes": 660,
      "tasks_inside_sleep_windows": 0,
      "task_ids_inside_sleep_windows": [],
      "fatigue_level": "elevated_concern",
      "fatigue_source": "assessment:assessment-demo",
      "data_warning_count": 0,
      "data_warning_rule_ids": []
    },
    "conflict_count_delta": -1,
    "resolved_conflicts": [],
    "new_conflicts": [],
    "summary": "The proposed schedule has 1 fewer conflicts under the configured rules than the original schedule ... These are rule-based schedule metrics, not a fatigue prediction.",
    "note": "Fatigue was not re-predicted; this comparison reflects schedule rules only.",
    "config_keys": ["WOCL_START_HOUR", "WOCL_END_HOUR"]
  },
  "data_warnings": []
}
```

Notes:

- `resolved_conflicts` and `new_conflicts` contain full `Conflict` objects; they
  are shown empty above only for brevity.
- `fatigue_level` and `fatigue_source` are copied from the original context for
  **both** schedules. A what-if never re-predicts fatigue.
- The exact `note` string is fixed and tested.

### Errors

| Case | Result |
| --- | --- |
| Unknown crew | `404 crew_not_found` |
| Reversed or naive window | `422 validation_error` |
| Unknown operation `type` | `422 validation_error` (Pydantic) |
| Empty `operations` | `422 validation_error` (Pydantic) |
| Unknown task id | `422 validation_error` with `details.operation_index` and `details.operation_type` |
| `delay_task` with `minutes <= 0` | `422 validation_error` (Pydantic) |
| `redistribute_workload` on a non-demanding task | `422 validation_error` |
| `add_recovery_period` splitting an existing task | `422 validation_error` |

---

## 8. Follow-ups

### 8.1 `POST /crew/{crew_id}/mission-intel/follow-ups`

Create an advisory follow-up from a recommendation in the current evaluation.

#### Request body

```json
{
  "recommendation_id": "rc_9c36a4fae6115c14",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "due_at": "2026-11-14T12:00:00Z"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `recommendation_id` | yes | Must be produced by regenerating recommendations over the supplied window. |
| `window_start` / `window_end` | together, optional | Default is now to now + `PLANNING_HORIZON_HOURS`. Supply the window used for the originating recommendation so ids stay reproducible. |
| `due_at` | no | Advisory reminder time only; no reminder is scheduled. |

#### Response `201`

```json
{
  "follow_up": {
    "follow_up_id": "fu_cd4917ea682b4352a001292a7fe18d63",
    "crew_id": "crew-demo-01",
    "recommendation_id": "rc_9c36a4fae6115c14",
    "related_conflict_id": "cf_05469e92ad39bb99",
    "countermeasure_id": "CM-02",
    "countermeasure_name": "Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough",
    "rule_id": "R-FATIGUE-CRITICAL-01",
    "status": "suggested",
    "requires_mission_approval": true,
    "requires_medical_review": true,
    "approved": null,
    "due_at": "2026-11-14T12:00:00Z",
    "result": null,
    "advisory_text": "Consider moving the critical task ... This is advisory decision support only; decisions remain with the crew, mission control, and medical staff.",
    "created_at": "2026-11-13T20:44:45.586770Z",
    "updated_at": "2026-11-13T20:44:45.586770Z"
  },
  "data_warnings": [
    {
      "code": "follow_up_store_is_process_local",
      "message": "Follow-ups are stored in process memory for this phase; they are cleared when the API process restarts. No mission task is changed by a follow-up.",
      "rule_id": null,
      "task_id": null
    }
  ]
}
```

Errors: `404 crew_not_found`, `404 recommendation_not_found`,
`422 validation_error` (only one half of the window supplied, reversed window,
unknown action later).

### 8.2 `PATCH /crew/{crew_id}/mission-intel/follow-ups/{follow_up_id}`

#### Request body

```json
{
  "action": "complete",
  "approved": true,
  "result": "Mission control reviewed the advisory."
}
```

Only `action`, `approved`, and `result` are accepted; unknown fields are
rejected. `result` is capped at 2000 characters.

| Field | Required | Notes |
| --- | --- | --- |
| `action` | yes | `accept`, `skip`, or `complete`. |
| `approved` | no | Required as `true` (now or on an earlier request) to complete an approval-gated follow-up. |
| `result` | no | Free-text outcome. Stored verbatim. |

#### State machine

| Current | `accept` | `skip` | `complete` |
| --- | --- | --- | --- |
| `suggested` | -> `accepted` | -> `skipped` | -> `completed` (requires approval) |
| `accepted` | 409 | -> `skipped` | -> `completed` (requires approval) |
| `skipped` | 409 | 409 | 409 |
| `completed` | 409 | 409 | 409 |

`skipped` and `completed` are terminal.

#### Response `200`

The same `FollowUpResponse` shape as create, with the updated `status`,
`approved`, `result`, and `updated_at`. `data_warnings` always contains
`follow_up_store_is_process_local`; the evaluation warnings are not re-emitted
on patch because no mission data were read.

#### Errors

| Case | Result |
| --- | --- |
| Unknown crew | `404 crew_not_found` |
| Unknown follow-up, or owned by another crew | `404 follow_up_not_found` |
| Disallowed transition | `409 invalid_status_transition` with `details.current_status` and `details.requested_status` |
| Complete without approval | `422 mission_approval_required` |
| Unknown `action` | `422 validation_error` |

Completing a follow-up never changes a mission task. It only records the
decision.

---

## 9. Follow-up storage limitation

Follow-ups are stored in a module-level, lock-protected dictionary in
`app/mission/followups.py`. They survive for the lifetime of the API process and
are cleared on restart. **This is a deliberate Phase 7 limitation, not a hidden
assumption**, and it is reported on every follow-up response as
`follow_up_store_is_process_local`.

Why the database is not used yet:

- The existing `ActionHistory` table has no `recommendation_id` or `rule_id`
  column, so the contract in this document cannot be reconstructed from a stored
  row.
- `ActionHistory.countermeasure_id` is a foreign key to `Countermeasure`, and
  the demo seed does not populate that catalogue. Writing an action would either
  lose the recommendation link or require creating catalogue rows during a
  request.
- Phase 7 may not change the schema.

A persistent implementation can replace `followups.py` without changing the HTTP
contract once a storage decision is approved. See
[Section 10](#10-person-2-databaseapi-needs).

---

## 10. Person 2 database/API needs

Requests are ordered by how much they limit the current contract. "Optional"
means the mission layer already works without it by using a documented
configurable assumption.

### P0 — correctness gaps that affect results today

1. **A task-overlap query helper.** `get_upcoming_tasks` returns only tasks that
   *start* inside the window. A task that starts before `window_start` and
   overlaps into it is invisible to the schedule, conflicts, and what-if
   endpoints. Requested helper:
   `get_tasks_overlapping(session, crew_id, start, end) -> list[MissionTask]`
   with `start_time < end AND end_time > start`. Until then this limitation is
   documented in `adapters.build_context` and in the schedule endpoint.
2. **`MissionTask.status`.** The database has no status column, so
   `adapters.task_from_db` assigns `DEFAULT_TASK_STATUS = planned` to every row.
   Completed/cancelled tasks therefore continue to drive conflicts. Requested
   field: `status` with `planned | in_progress | completed | cancelled`.
3. **Persistent follow-up linkage.** For a DB-backed follow-up store, request
   either:
   - add `recommendation_id: str | None` and `rule_id: str | None` to
     `ActionHistory`, plus make `countermeasure_id` nullable or populate the
     `Countermeasure` catalogue with CM-01 ... CM-07; or
   - approve a dedicated `MissionFollowUp` table. Either way, the current
     in-memory store can be replaced without changing this API.

### P1 — improves fidelity, optional until delivered

4. **`MissionTask.priority`** (`low | medium | high | critical`). Currently
   derived from workload and `is_critical` through `PRIORITY_BY_WORKLOAD` and
   `CRITICAL_PRIORITY`.
5. **`MissionTask.required_alertness`** (1–5). Currently derived through
   `ALERTNESS_BY_WORKLOAD` and `CRITICAL_TASK_ALERTNESS_REQUIREMENT`.
6. **Task categories.** The database `TaskType` lacks `sleep`, `communication`,
   and `rest_recovery`. Add them if the mission plan contains explicit sleep or
   recovery blocks. Until then sleep windows are inferred from `SleepRecord`, and
   recovery blocks exist only inside a what-if scenario.
7. **Crew clock reference.** Add a per-crew UTC offset or sleep-phase reference
   (for example `mission_clock_offset_minutes`) so circadian and habitual-sleep
   rules do not assume UTC clock placement. All current clock rules are
   documented as configurable assumptions.
8. **Task notes in the API.** `MissionTask.notes` is stored but not returned by
   `task_from_db`. Returning it would help reviewers without affecting any rule.

### P2 — future work, no current blocker

9. A stable mission identifier or mission phase on tasks, so recommendations can
   be grouped per mission.
10. A read endpoint for the `Countermeasure` catalogue once it is seeded, so the
    UI can explain CM-01 ... CM-07 from the database instead of the fixed table
    in `recommendations.py`.

---

## 11. Person 3 assessment needs

The mission layer consumes the latest `Assessment` through
`AssessmentFatigueProvider`:

```text
Assessment.status -> FatigueLevel
insufficient_data -> unknown
no_flag           -> no_flag
monitor           -> monitor
elevated_concern  -> elevated_concern
```

No numeric score is read today. This is deliberate: the mission rules must not
turn an undocumented number into a severity or a diagnosis.

Requests, all optional until Person 3 confirms semantics:

1. **Keep `Assessment.status` values stable.** The mapping above is the only
   fatigue input. A new status value falls back to `unknown`.
2. **Document `contributing_factors`.** The field is currently arbitrary JSON and
   is passed through verbatim in `fatigue_signal.contributing_factors`. If a
   stable shape is available, the mission layer can display factor names. A
   proposed optional shape (not required, not assumed):
   ```json
   {
     "factor": "sleep_debt",
     "direction": "increases_concern",
     "value": 320,
     "unit": "minutes",
     "rule_id": "R-SLEEP-DEBT-01",
     "source_id": "NASA-HRP-Sleep-Risk"
   }
   ```
   `factor`, `direction`, `value`, and `unit` are proposals only.
3. **If a numeric score is delivered, document it.** Required metadata before
   the mission layer can consume it:
   - `score` (number),
   - `scale_min` and `scale_max`,
   - `direction` (`higher_is_worse` or `higher_is_better`),
   - `thresholds` and their evidence status,
   - `engine_version`.
   A numeric score would still **not** be used to diagnose, and no threshold
   would be hard-coded in the mission layer; it would have to be added to
   `config.py` with an evidence label first.
4. **Assessment freshness.** The mission layer uses the latest assessment
   regardless of age. Request either an `Assessment.valid_until` field or an
   agreed freshness threshold for `config.py`. Until one exists, `source` shows
   the assessment id so a reviewer can see which row was used.
5. **`insufficient_data` must mean "no judgement".** The mission layer reports it
   as `assessment_insufficient_data` and never treats it as `no_flag`.
6. **`engine_version` and `created_at`** are used for traceability only.

### Optional-until-delivered summary

| Owner | Field / behaviour | Current fallback |
| --- | --- | --- |
| Person 2 | `MissionTask.status` | `DEFAULT_TASK_STATUS = planned` |
| Person 2 | `MissionTask.priority` | Derived from workload and `is_critical` |
| Person 2 | `MissionTask.required_alertness` | Derived from workload and `is_critical` |
| Person 2 | Task categories `sleep`, `communication`, `rest_recovery` | Sleep inferred from `SleepRecord`; recovery only in what-if |
| Person 2 | Crew clock/sleep-phase reference | UTC clock assumptions in `config.py` |
| Person 2 | Overlap query for tasks starting before the window | Start-only loading, documented limitation |
| Person 2 | Persistent follow-up storage | Process-local store with warning |
| Person 3 | Structured `contributing_factors` | Passed through verbatim |
| Person 3 | Numeric score with documented scale | Not read |
| Person 3 | `Assessment.valid_until` / freshness | Latest row used, id exposed in `source` |

---

## 12. Integration status

These edits are outside `backend/app/mission/`. Both edits described below are
applied.

### 12.1 Router registration (applied)

Approved after Phase 9. `backend/app/routers/__init__.py` now imports and
registers the mission router:

`backend/app/routers/__init__.py`:

```python
"""Router registry: adding a router is one line here."""

from app.mission.router import router as mission_intel_router
from app.routers import assessments, checkins, crew, demo, history, missions

ROUTERS = [
    crew.router,
    checkins.router,
    history.router,
    missions.router,
    assessments.router,
    demo.router,
    mission_intel_router,
]
```

This exposes every route under `/api/v1/crew/{crew_id}/mission-intel`.

### 12.2 Non-blocking warnings in `mission_service.py` (applied)

Approved and applied after Phase 9.

`backend/app/services/mission_service.py`, `create_task`, after
`session.commit()` and before `return task`:

```python
    log_task_warnings(
        session,
        crew_id,
        task.start_time,
        task.end_time,
        task_type=task.task_type,
        workload_level=task.workload_level,
        is_critical=task.is_critical,
        title=task.title,
        exclude_task_id=task.id,
    )
    return task
```

`update_task`, after `session.commit()` and before `return task`:

```python
    log_task_warnings(
        session,
        task.crew_id,
        task.start_time,
        task.end_time,
        task_type=task.task_type,
        workload_level=task.workload_level,
        is_critical=task.is_critical,
        title=task.title,
        exclude_task_id=task.id,
    )
    return task
```

with the import:

```python
from app.mission.task_checks import log_task_warnings
```

Behaviour:

- The helper only logs `WARNING` lines. It never raises for a rule finding and
  never rejects a task.
- Unknown crews and invalid windows fail open, so the service's existing `404`
  and `422` validation remains the source of truth.
- Both calls pass `exclude_task_id=task.id`; `create_task` commits first, so the
  new row would otherwise be compared with itself, and `update_task` must not
  conflict with the row it replaces.
- No database write occurs in the helper.

---

## 13. Tests

`app/mission/tests/test_api.py` covers every endpoint, the shared error body,
`data_warnings`, the what-if comparison, the follow-up lifecycle and approval
gate, deterministic ids, and the process-local warning.
`app/mission/tests/test_task_checks.py` covers the non-blocking helper.

Run from `backend/`:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q
```

Expected at the time of writing: all mission tests pass. The only warning is
the pre-existing Starlette `TestClient` deprecation notice.
