# Phase 9 — Dashboard Data Requirements (Person 1 hand-off)

Status: **documentation only**. This document tells Person 1 (React) exactly
which mission-intelligence endpoints to call, which fields to render, what a real
response looks like, and how to refresh and fail safely. It adds no React code
and changes no backend contract.

The authoritative contract is
[`05_api_contracts.md`](./05_api_contracts.md). The screen layout and state rules
are in [`07_ux_spec.md`](./07_ux_spec.md). If this document and the router ever
disagree, the router and `05_api_contracts.md` win.

> **Decision support only.** No screen may diagnose, score fatigue numerically,
> recommend medication, or claim that a schedule change improves fatigue.

---

## 1. Current integration status

| Item | State |
| --- | --- |
| Router implemented | Yes — `backend/app/mission/router.py` |
| Router registered in `app/routers/__init__.py` | **Yes** — approved and applied after Phase 9 |
| Mount path | `/api/v1/crew/{crew_id}/mission-intel/...` |
| Data source | Read-only `history_service` + latest `Assessment`; follow-ups in process memory |
| Authentication | None in this phase (same as the rest of the API) |
| CORS | `CORS_ORIGINS` in `app/core/config.py`, default `http://localhost:5173,http://localhost:3000` |
| Real-time push | None. Request/response only |

The routes are reachable through `app.main:app` when the API is running. The
mission end-to-end tests also mount the router explicitly so they remain
independent of the registry.

Base URL used in this document:

```text
http://127.0.0.1:8000/api/v1
```

---

## 2. Endpoint summary

All endpoints are crew-scoped. There is no global mission-intelligence endpoint.

| # | Method | Path | Purpose | Screens |
| --- | --- | --- | --- | --- |
| 1 | `GET` | `/crew/{crew_id}/mission-intel/schedule` | Daily/weekly schedule, sleep bands | Mission Calendar |
| 2 | `GET` | `/crew/{crew_id}/mission-intel/overview` | Health, tasks + suitability, counts | Overview, Upcoming Tasks, Fatigue Alerts |
| 3 | `GET` | `/crew/{crew_id}/mission-intel/conflicts` | Rule findings | Calendar overlay, Conflicts, Fatigue Alerts |
| 4 | `GET` | `/crew/{crew_id}/mission-intel/recommendations` | Advisories | Recommendations, Overview top-3, Fatigue Alerts |
| 5 | `POST` | `/crew/{crew_id}/mission-intel/what-if` | Transient comparison | What-if |
| 6 | `POST` | `/crew/{crew_id}/mission-intel/follow-ups` | Create advisory follow-up | Recommendations → Follow-ups |
| 7 | `PATCH` | `/crew/{crew_id}/mission-intel/follow-ups/{follow_up_id}` | Accept/skip/complete | Follow-ups |

There is **no** `GET /follow-ups`, no single-conflict endpoint, no
single-recommendation endpoint, and no countermeasure-catalogue endpoint. Do not
invent them.

### 2.1 Window rules

- Every datetime must be RFC 3339 with an explicit offset; `Z` is accepted and
  preferred.
- Naive datetimes are rejected with `422`.
- `window_end` must be after `window_start`.
- `#1` uses `date` + `view`, not a window.
- `#2`, `#3`, `#4`, `#5`, `#6` use `window_start` / `window_end`.
- For reproducible scenario data always send
  `window_start=2026-11-13T00:00:00Z` and
  `window_end=2026-11-14T00:00:00Z`.
- When omitted, overview/conflicts/recommendations default to “now” to
  “now + 72 h” (`PLANNING_HORIZON_HOURS`, configurable assumption). Defaults
  are not reproducible against fixed scenario fixtures, so the demo must send an
  explicit window.

### 2.2 Determinism

- `Conflict.conflict_id`, `Recommendation.recommendation_id` are deterministic
  hashes of the inputs.
- The same crew + same window + unchanged data returns the same ids.
- Recommendation ids change if the window changes or the underlying tasks,
  sleep, or assessment change. A follow-up must send the **same window** that
  produced its recommendation, or the create call returns
  `404 recommendation_not_found`.

---

## 3. Common response shapes

### 3.1 Success

Every successful response is a flat object with the payload plus
`data_warnings` at the top level.

```json
{
  "…": "endpoint-specific fields",
  "data_warnings": []
}
```

### 3.2 Warning object

```json
{
  "code": "no_assessment_available",
  "message": "No Assessment row is available for this crew member, so the fatigue level is 'unknown'.",
  "rule_id": null,
  "task_id": null
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `code` | string | Stable enum-ish code; see §6. |
| `message` | string | Human-readable; safe to display verbatim. |
| `rule_id` | string \| null | Present for `conflict_data_warning`. |
| `task_id` | string \| null | Present when the warning is tied to one task. |

### 3.3 Error

Every error has exactly this shape, including `data_warnings`:

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

`details` may be `null`, an object, or a list (Pydantic validation errors).

---

## 4. Endpoint details and exact examples

The JSON below was captured from the real router against an isolated in-memory
database seeded with the six Phase 8 scenarios. Values are exact.

### 4.0 Test crew ids

| Scenario | `crew_id` | Display name |
| --- | --- | --- |
| `normal_sleep` | `crew-mission-01` | Mira Sol |
| `sleep_deprivation` | `crew-mission-02` | Tomas Reed |
| `high_workload` | `crew-mission-03` | Anya Novak |
| `sleep_mission_conflict` | `crew-mission-04` | Idris Kane |
| `high_fatigue_before_critical` | `crew-mission-05` | Lea Fontaine |
| `recovery_scheduling` | `crew-mission-06` | Noah Brandt |

Seed them from `backend/` with:

```powershell
& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --reset
```

---

### 4.1 `GET /crew/{crew_id}/mission-intel/schedule`

**Query**

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `view` | `daily` \| `weekly` | `daily` | Weekly = 7 days starting at `date`, not forced to Monday. |
| `date` | `YYYY-MM-DD` | today UTC | Anchor date. |

**Example request**

```text
GET /api/v1/crew/crew-mission-04/mission-intel/schedule?view=daily&date=2026-11-13
```

**Example response `200`**

```json
{
  "crew_id": "crew-mission-04",
  "view": "daily",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "tasks": [
    {
      "task_id": "crew-mission-04-task-day",
      "astronaut_id": "crew-mission-04",
      "name": "Science sample analysis",
      "category": "science",
      "start_time": "2026-11-13T10:00:00Z",
      "end_time": "2026-11-13T11:00:00Z",
      "priority": "medium",
      "workload_level": "medium",
      "required_alertness": 3,
      "status": "planned",
      "is_critical": false,
      "duration_minutes": 60
    },
    {
      "task_id": "crew-mission-04-task-night",
      "astronaut_id": "crew-mission-04",
      "name": "Night maintenance",
      "category": "maintenance",
      "start_time": "2026-11-13T23:00:00Z",
      "end_time": "2026-11-14T00:00:00Z",
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

**Field notes**

- `tasks[]` contains only tasks that **start** inside the window.
- `status` is always `planned` today; `MissionTask` has no status column.
- `priority` and `required_alertness` are derived (see
  `05_api_contracts.md` §10), not stored mission fields.
- `planned_sleep_windows[]` is inferred from at least
  `HABITUAL_SLEEP_MIN_RECORDS = 3` consistent sleep records. It is not a mission
  planning input.

---

### 4.2 `GET /crew/{crew_id}/mission-intel/overview`

**Query**

| Name | Type | Default |
| --- | --- | --- |
| `window_start` | datetime | now UTC |
| `window_end` | datetime | now + 72 h |

**Example request**

```text
GET /api/v1/crew/crew-mission-05/mission-intel/overview?window_start=2026-11-13T00:00:00Z&window_end=2026-11-14T00:00:00Z
```

**Example response `200`**

```json
{
  "crew": {
    "crew_id": "crew-mission-05",
    "display_name": "Lea Fontaine",
    "role": "EVA Specialist",
    "sleep_target_hours": 8.0
  },
  "health": {
    "fatigue_signal": {
      "level": "elevated_concern",
      "source": "assessment:crew-mission-05-assessment",
      "contributing_factors": [
        {
          "source": "simulated",
          "synthetic_test_data": true,
          "model_output": false,
          "scenario": "high_fatigue_before_critical"
        }
      ]
    },
    "latest_sleep": {
      "sleep_id": "crew-mission-05-sleep-03",
      "start_time": "2026-11-12T22:00:00Z",
      "end_time": "2026-11-13T06:00:00Z",
      "interruptions": 0,
      "quality": "valid",
      "duration_minutes": 480
    },
    "recent_sleep": [
      {
        "sleep_id": "crew-mission-05-sleep-03",
        "start_time": "2026-11-12T22:00:00Z",
        "end_time": "2026-11-13T06:00:00Z",
        "interruptions": 0,
        "quality": "valid",
        "duration_minutes": 480
      },
      {
        "sleep_id": "crew-mission-05-sleep-02",
        "start_time": "2026-11-11T22:00:00Z",
        "end_time": "2026-11-12T06:00:00Z",
        "interruptions": 0,
        "quality": "valid",
        "duration_minutes": 480
      },
      {
        "sleep_id": "crew-mission-05-sleep-01",
        "start_time": "2026-11-10T22:00:00Z",
        "end_time": "2026-11-11T06:00:00Z",
        "interruptions": 0,
        "quality": "valid",
        "duration_minutes": 480
      }
    ],
    "planned_sleep_windows": [
      {
        "start_time": "2026-11-13T22:00:00Z",
        "end_time": "2026-11-14T06:00:00Z",
        "source": "inferred_habitual_sleep",
        "duration_minutes": 480
      }
    ]
  },
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "upcoming_tasks": [
    {
      "task": {
        "task_id": "crew-mission-05-task-eva",
        "astronaut_id": "crew-mission-05",
        "name": "Critical EVA - solar array inspection",
        "category": "eva",
        "start_time": "2026-11-13T09:00:00Z",
        "end_time": "2026-11-13T13:00:00Z",
        "priority": "critical",
        "workload_level": "high",
        "required_alertness": 5,
        "status": "planned",
        "is_critical": true,
        "duration_minutes": 240
      },
      "suitability": {
        "task_id": "crew-mission-05-task-eva",
        "astronaut_id": "crew-mission-05",
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
          "priority": "critical",
          "workload_level": "high",
          "is_critical": true,
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
    },
    {
      "task": {
        "task_id": "crew-mission-05-task-review",
        "astronaut_id": "crew-mission-05",
        "name": "Procedure review",
        "category": "other",
        "start_time": "2026-11-13T15:00:00Z",
        "end_time": "2026-11-13T16:00:00Z",
        "priority": "low",
        "workload_level": "low",
        "required_alertness": 2,
        "status": "planned",
        "is_critical": false,
        "duration_minutes": 60
      },
      "suitability": {
        "task_id": "crew-mission-05-task-review",
        "astronaut_id": "crew-mission-05",
        "status": "review",
        "reasons": [
          "R-FATIGUE-02: Fatigue level 'elevated_concern' warrants review even for a non-demanding task."
        ],
        "rule_ids": ["R-FATIGUE-02"],
        "inputs_used": {
          "fatigue_level": "elevated_concern",
          "last_sleep_minutes": 480,
          "sleep_target_minutes": 480,
          "sleep_ratio": 1.0,
          "required_alertness": 2,
          "priority": "low",
          "workload_level": "low",
          "is_critical": false,
          "demanding": false,
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
  "conflict_count": 1,
  "recommendation_count": 1,
  "data_warnings": []
}
```

**Field notes**

- `health.fatigue_signal.level` is one of `unknown`, `no_flag`, `monitor`,
  `elevated_concern`. There is **no numeric score**.
- `contributing_factors` is arbitrary JSON passed through verbatim. Render it
  generically; do not assume `factor`/`value` keys exist. The Phase 8 payload
  above is fixture provenance, not a model explanation.
- `quality` is `valid`, `questionable`, or `missing`.
- `suitability.status` is `suitable`, `review`, `not_recommended`, or
  `insufficient_data`.
- `suitability.inputs_used` is an open object. `thresholds` may be present, but
  treat every key defensively.
- `conflict_count` and `recommendation_count` are the only counts `overview`
  returns. Severity and per-type breakdown require §4.3.
- The fixture `contributing_factors` includes `model_output: false`. Scenario 5’s
  `elevated_concern` value is seeded synthetic input, **not** AI model output.

---

### 4.3 `GET /crew/{crew_id}/mission-intel/conflicts`

**Query:** `window_start`, `window_end` (same rules as §4.2).

**Example request**

```text
GET /api/v1/crew/crew-mission-05/mission-intel/conflicts?window_start=2026-11-13T00:00:00Z&window_end=2026-11-14T00:00:00Z
```

**Example response `200`**

```json
{
  "crew_id": "crew-mission-05",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "rule_set_version": "mission-conflicts/1.0",
  "conflicts": [
    {
      "conflict_id": "cf_dcf1eebd43a42ea6",
      "rule_id": "R-FATIGUE-CRITICAL-01",
      "conflict_type": "high_fatigue_critical_task",
      "severity": "critical",
      "astronaut_id": "crew-mission-05",
      "task_ids": ["crew-mission-05-task-eva"],
      "affected_start": "2026-11-13T09:00:00Z",
      "affected_end": "2026-11-13T13:00:00Z",
      "explanation": "Rule R-FATIGUE-CRITICAL-01: recorded fatigue level is 'elevated_concern' (source 'assessment:crew-mission-05-assessment') and task 'crew-mission-05-task-eva' (Critical EVA - solar array inspection) is critical or high-alertness (critical flag=True, priority=critical, required alertness=5, threshold 4).",
      "suggested_action": "Review the task assignment or timing under rule R-FATIGUE-CRITICAL-01; rescheduling or adding a recovery opportunity may reduce risk. Advisory only; final authority remains with the crew, flight surgeon, and mission control.",
      "source_ids": ["NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"],
      "config_keys": ["CRITICAL_TASK_ALERTNESS_REQUIREMENT"],
      "task_id": "crew-mission-05-task-eva"
    }
  ],
  "config_keys": ["CRITICAL_TASK_ALERTNESS_REQUIREMENT"],
  "data_warnings": []
}
```

**Field notes**

- Ordering: `affected_start`, then severity (highest first), then
  `conflict_id`. Keep the API order; label any client re-sort.
- `task_id` equals `task_ids[0]` for convenience.
- `affected_start == affected_end` is possible (for example a zero-minute free
  gap). Render it as a pin / “0 min gap” marker, not a block.
- `severity` ∈ `low`, `medium`, `high`, `critical`.
- `conflict_type` ∈ `sleep_window_conflict`, `insufficient_recovery_gap`,
  `high_fatigue_critical_task`, `workload_overload`,
  `circadian_low_alertness`.
- `source_ids` and `config_keys` are traceability only, not user-facing
  thresholds.

---

### 4.4 `GET /crew/{crew_id}/mission-intel/recommendations`

**Query:** `window_start`, `window_end`.

**Example request**

```text
GET /api/v1/crew/crew-mission-05/mission-intel/recommendations?window_start=2026-11-13T00:00:00Z&window_end=2026-11-14T00:00:00Z
```

**Example response `200`**

```json
{
  "crew_id": "crew-mission-05",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
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
      "reason": "Rule R-FATIGUE-CRITICAL-01 reports fatigue level 'elevated_concern' (source 'assessment:crew-mission-05-assessment') before task 'crew-mission-05-task-eva' (Critical EVA - solar array inspection) from 2026-11-13 09:00 UTC to 2026-11-13 13:00 UTC. The task requires alertness 5 on the project scale.",
      "suggested_action": "Consider moving the critical task to a different schedule window or inserting a recovery opportunity before it. Review under rule R-FATIGUE-CRITICAL-01; this may reduce risk under rule R-FATIGUE-CRITICAL-01.",
      "expected_benefit": "Removes the co-occurrence of a 'elevated_concern' fatigue signal with a critical task under rule R-FATIGUE-CRITICAL-01; no physiological effect is claimed.",
      "priority": "critical",
      "explanation": "The fatigue input is a categorical assessment signal, not a measurement of impairment. The recommendation reviews timing only and does not propose any clinical action.",
      "source_ids": ["NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"],
      "preconditions": [
        "Mission planner and, when flagged, medical staff review the task timing."
      ],
      "warnings": [
        "The recorded fatigue level is 'elevated_concern'; a medical review is flagged for this advisory."
      ],
      "requires_mission_approval": true,
      "requires_medical_review": true,
      "advisory_text": "Consider moving the critical task to a different schedule window or inserting a recovery opportunity before it. Review under rule R-FATIGUE-CRITICAL-01; this may reduce risk under rule R-FATIGUE-CRITICAL-01. This is advisory decision support only; decisions remain with the crew, mission control, and medical staff."
    }
  ],
  "data_warnings": []
}
```

**Field notes**

- Maximum 5 recommendations (`MAX_RECOMMENDATIONS_PER_RESPONSE`, configurable
  assumption). `conflict_count` may be higher than `recommendations.length`.
- `countermeasure_id` is always `CM-01` … `CM-07`.
- `requires_mission_approval` is always `true`.
- `requires_medical_review` is `true` only when the advisory depends on
  `elevated_concern`. Never infer it client-side.
- A conflict may have no advisory. Match by `related_conflict_id` and show “No
  mapped advisory for this finding” when there is no match.
- Display `advisory_text` or the individual fields verbatim; do not add stronger
  claims.

---

### 4.5 `POST /crew/{crew_id}/mission-intel/what-if`

**Request body**

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

Supported `type` values and fields:

| `type` | Fields | Notes |
| --- | --- | --- |
| `delay_task` | `task_id`, `minutes > 0` | Whole minutes, later only. |
| `move_task` | `task_id`, `new_start` | Preserves duration. |
| `add_recovery_period` | `start`, `end`, `shift_following_tasks` (default `true`), optional `task_id`, optional `name` | Inserts a `rest_recovery` block. |
| `redistribute_workload` | `task_id`, `new_start` | Rejects non-demanding tasks. |
| `modify_sleep_window` | `new_start`, `new_end`, `window_index` (default `0`) | Replaces one planned/inferred sleep window. |

`operations` length must be 1–20. Order is preserved and applied sequentially.

**Example response `200` (abridged)**

```json
{
  "crew_id": "crew-mission-06",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "applied_operations": [
    { "index": 0, "type": "add_recovery_period", "task_id": null }
  ],
  "comparison": {
    "original_metrics": {
      "evaluation_start": "2026-11-13T00:00:00Z",
      "evaluation_end": "2026-11-14T00:00:00Z",
      "conflicts_by_type": [
        {
          "conflict_type": "insufficient_recovery_gap",
          "count": 1,
          "highest_severity": "high",
          "severity_counts": { "high": 1 }
        }
      ],
      "total_conflicts": 1,
      "highest_severity": "high",
      "workload_windows": [
        {
          "window_start": "2026-11-13T08:00:00Z",
          "window_end": "2026-11-14T08:00:00Z",
          "demanding_task_count": 2,
          "demanding_minutes": 120,
          "exceeds_task_limit": false,
          "exceeds_minutes_limit": false,
          "task_ids": [
            "crew-mission-06-task-demanding-a",
            "crew-mission-06-task-demanding-b"
          ]
        }
      ],
      "total_free_minutes": 1260,
      "total_recovery_minutes": 0,
      "total_recovery_and_free_minutes": 1260,
      "longest_recovery_gap_minutes": 600,
      "tasks_inside_sleep_windows": 0,
      "task_ids_inside_sleep_windows": [],
      "fatigue_level": "no_flag",
      "fatigue_source": "assessment:crew-mission-06-assessment",
      "data_warning_count": 0,
      "data_warning_rule_ids": []
    },
    "proposed_metrics": {
      "evaluation_start": "2026-11-13T00:00:00Z",
      "evaluation_end": "2026-11-14T00:00:00Z",
      "conflicts_by_type": [],
      "total_conflicts": 0,
      "highest_severity": null,
      "workload_windows": [
        {
          "window_start": "2026-11-13T08:00:00Z",
          "window_end": "2026-11-14T08:00:00Z",
          "demanding_task_count": 2,
          "demanding_minutes": 120,
          "exceeds_task_limit": false,
          "exceeds_minutes_limit": false,
          "task_ids": [
            "crew-mission-06-task-demanding-a",
            "crew-mission-06-task-demanding-b"
          ]
        }
      ],
      "total_free_minutes": 1230,
      "total_recovery_minutes": 30,
      "total_recovery_and_free_minutes": 1260,
      "longest_recovery_gap_minutes": 570,
      "tasks_inside_sleep_windows": 0,
      "task_ids_inside_sleep_windows": [],
      "fatigue_level": "no_flag",
      "fatigue_source": "assessment:crew-mission-06-assessment",
      "data_warning_count": 0,
      "data_warning_rule_ids": []
    },
    "conflict_count_delta": -1,
    "resolved_conflicts": [
      {
        "conflict_id": "cf_773c6f2af523c905",
        "rule_id": "R-RECOVERY-01",
        "conflict_type": "insufficient_recovery_gap",
        "severity": "high",
        "astronaut_id": "crew-mission-06",
        "task_ids": [
          "crew-mission-06-task-demanding-a",
          "crew-mission-06-task-demanding-b"
        ],
        "affected_start": "2026-11-13T09:00:00Z",
        "affected_end": "2026-11-13T09:10:00Z",
        "explanation": "Rule R-RECOVERY-01: demanding task 'crew-mission-06-task-demanding-b' starts at 2026-11-13T09:10:00+00:00, only 10 free min after demanding task 'crew-mission-06-task-demanding-a' ends at 2026-11-13T09:00:00+00:00. The configured minimum recovery gap is 30 min.",
        "suggested_action": "Review inserting a structured recovery break or moving one of the demanding tasks under rule R-RECOVERY-01; a recovery gap may reduce risk. Advisory only.",
        "source_ids": ["NASA-TM-Fatigue-Countermeasures", "NASA-STD-3001-Vol2"],
        "config_keys": [
          "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
          "DEMANDING_WORKLOAD_LEVELS",
          "MIN_RECOVERY_GAP_MINUTES"
        ],
        "task_id": "crew-mission-06-task-demanding-a"
      }
    ],
    "new_conflicts": [],
    "summary": "The proposed schedule has 1 fewer conflicts under the configured rules than the original schedule (1 original, 0 proposed; 1 resolved and 0 new conflict(s)). Free time is 1260 min original vs 1230 min proposed; recovery time is 0 min vs 30 min; the longest recovery gap is 600 min vs 570 min. These are rule-based schedule metrics, not a fatigue prediction.",
    "note": "Fatigue was not re-predicted; this comparison reflects schedule rules only.",
    "config_keys": [
      "CONFLICT_OVERLAP_TOLERANCE_MINUTES",
      "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
      "DEMANDING_WORKLOAD_LEVELS",
      "MAX_DEMANDING_TASKS_PER_WINDOW",
      "MAX_DEMANDING_TASK_HOURS_PER_WINDOW",
      "MIN_RECOVERY_GAP_MINUTES",
      "SLEEP_SHORTFALL_REVIEW_RATIO",
      "WORKLOAD_WINDOW_HOURS"
    ]
  },
  "data_warnings": []
}
```

**Field notes**

- `comparison.note` is a fixed, tested string. Render it verbatim.
- `fatigue_level` / `fatigue_source` are copied from the original context into
  both metric objects. Do not present them as a post-edit result.
- `conflict_count_delta = proposed − original`. Negative is fewer conflicts.
- `resolved_conflicts` / `new_conflicts` contain full conflict objects.
- Nothing is persisted; the original schedule is never mutated.

---

### 4.6 `POST /crew/{crew_id}/mission-intel/follow-ups`

**Request body**

```json
{
  "recommendation_id": "rc_6fedabfc95e825ce",
  "window_start": "2026-11-13T00:00:00Z",
  "window_end": "2026-11-14T00:00:00Z",
  "due_at": "2026-11-14T12:00:00Z"
}
```

**Response `201`**

```json
{
  "follow_up": {
    "follow_up_id": "fu_1761d51df6314dc79c85177acd7eddc0",
    "crew_id": "crew-mission-06",
    "recommendation_id": "rc_6fedabfc95e825ce",
    "related_conflict_id": "cf_773c6f2af523c905",
    "countermeasure_id": "CM-03",
    "countermeasure_name": "Insert Structured Recovery / Rest Break Between Demanding Tasks",
    "rule_id": "R-RECOVERY-01",
    "status": "suggested",
    "requires_mission_approval": true,
    "requires_medical_review": false,
    "approved": null,
    "due_at": "2026-11-14T12:00:00Z",
    "result": null,
    "advisory_text": "Consider placing a structured recovery break of at least 15 min in the free interval starting 2026-11-13 10:10 UTC (170 min available). Review under rule R-RECOVERY-01; this may reduce risk under rule R-RECOVERY-01. This is advisory decision support only; decisions remain with the crew, mission control, and medical staff.",
    "created_at": "2026-11-13T21:08:09.819421Z",
    "updated_at": "2026-11-13T21:08:09.819421Z"
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

`follow_up_id` and timestamps are generated at request time; the example is a
real captured value, not a fixed fixture. `approved` is `null` until an approval
is recorded.

---

### 4.7 `PATCH /crew/{crew_id}/mission-intel/follow-ups/{follow_up_id}`

**Request body**

```json
{
  "action": "complete",
  "approved": true,
  "result": "Demo: mission control reviewed the advisory."
}
```

**Response `200` (excerpt)**

```json
{
  "follow_up": {
    "follow_up_id": "fu_1761d51df6314dc79c85177acd7eddc0",
    "crew_id": "crew-mission-06",
    "recommendation_id": "rc_6fedabfc95e825ce",
    "related_conflict_id": "cf_773c6f2af523c905",
    "countermeasure_id": "CM-03",
    "countermeasure_name": "Insert Structured Recovery / Rest Break Between Demanding Tasks",
    "rule_id": "R-RECOVERY-01",
    "status": "completed",
    "requires_mission_approval": true,
    "requires_medical_review": false,
    "approved": true,
    "due_at": "2026-11-14T12:00:00Z",
    "result": "Demo: mission control reviewed the advisory.",
    "advisory_text": "Consider placing a structured recovery break of at least 15 min … This is advisory decision support only; decisions remain with the crew, mission control, and medical staff.",
    "created_at": "2026-11-13T21:08:09.819421Z",
    "updated_at": "2026-11-13T21:08:09.832924Z"
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

**State machine**

| Current | `accept` | `skip` | `complete` |
| --- | --- | --- | --- |
| `suggested` | → `accepted` | → `skipped` | → `completed` (needs approval) |
| `accepted` | `409` | → `skipped` | → `completed` (needs approval) |
| `skipped` | `409` | `409` | `409` |
| `completed` | `409` | `409` | `409` |

`result` is capped at 2000 characters. Unknown fields are rejected.

---

## 5. Refresh and polling guidance

There is no websocket, SSE, or long-poll. Everything is request/response.

### 5.1 Fetch triggers

| Trigger | Endpoints to refetch |
| --- | --- |
| Route enters | That screen’s primary endpoint |
| Crew changes | All visible mission endpoints |
| Window changes | All visible mission endpoints, with a short debounce |
| Manual “Refresh” | Visible mission endpoints |
| After `POST /follow-ups` | Nothing required; merge the returned `follow_up` into client state |
| After `PATCH /follow-ups` | Nothing required; replace the record from the response |
| Router registered / app restarted | Full refetch; process-local follow-ups are gone |

### 5.2 Suggested intervals

| Situation | Interval | Notes |
| --- | --- | --- |
| Scenario demo / static fixtures | No auto-poll | Manual refresh only; data cannot change unless seeded |
| Local development without a simulator | 60 s | Minimum sensible interval; pause when the tab is hidden |
| Mission-control style dashboard | 60–120 s | Poll only the visible screen; do not poll all four lists in parallel |
| What-if | On submit only | Never poll; the edit is transient |

### 5.3 Caching

- Cache key: `crew_id` + `window_start` + `window_end` + endpoint (+ `date`/`view`
  for schedule, + request body hash for what-if).
- Suggested TTL: 60 s for reads; no caching for follow-up create/patch.
- Conflict and recommendation ids are deterministic, so re-fetching the same key
  is safe and produces stable keys for React lists.
- Cancel in-flight requests with `AbortController` when crew or window changes.
- Do not merge lists from different windows; recommendation ids are
  window-scoped.
- Pause timers when `document.visibilityState === "hidden"` and refetch on
  `visibilitychange` if the data is older than the TTL.

### 5.4 Request fan-out per screen

| Screen | Requests |
| --- | --- |
| Mission Calendar | `schedule` + `conflicts` (window from schedule) |
| Overview | `overview` + `recommendations` + optional `conflicts` for severity detail |
| Upcoming Tasks | `overview` only |
| Fatigue Alerts | `overview` + `conflicts` + `recommendations` |
| Schedule Conflicts | `conflicts` (+ `recommendations` only when opening an advisory) |
| Recommendations | `recommendations` |
| What-if | `POST what-if` only |
| Follow-ups | No read endpoint; use records from create/patch responses |

Do not call all endpoints on every screen. The fan-out above is the maximum
needed.

---

## 6. Warning and error handling

### 6.1 Warning codes

| `code` | Render | Effect on screen |
| --- | --- | --- |
| `no_assessment_available` | Persistent warning strip | Fatigue = `unknown`; fatigue-dependent cards use the unknown-data state |
| `assessment_insufficient_data` | Persistent warning strip | Fatigue = `unknown`; no judgement was made |
| `no_recent_sleep` | Persistent warning strip | Sleep card says “No recent sleep”; shortfall/recovery rules skipped |
| `no_planned_sleep_window` | Persistent warning strip | Sleep band unavailable; circadian rule used the configured fallback |
| `no_tasks_in_window` | Persistent warning strip | Empty state says no task **starts** in the window |
| `conflict_data_warning` | Persistent warning row, linked by `rule_id`/`task_id` | A rule was not evaluated; do not treat as “no conflict” |
| `follow_up_store_is_process_local` | Persistent notice on Follow-ups | Records are session-only; no `GET` list exists |
| Unknown code | “Data warning: <message>” + raw code in disclosure | Never drop it |

### 6.2 Error codes and retry policy

| HTTP | `error.code` | UI action | Retry? |
| --- | --- | --- | --- |
| 404 | `crew_not_found` | “Crew not found”; open crew selector | No |
| 404 | `recommendation_not_found` | “This recommendation is no longer in the current evaluation”; refetch recommendations with the same window | No (refetch instead) |
| 404 | `follow_up_not_found` | Remove the stale card; return to Recommendations | No |
| 409 | `invalid_status_transition` | Show `details.current_status`/`requested_status`; refresh the record | No |
| 422 | `mission_approval_required` | Show approval gate; resend with `approved: true` after confirmation | No |
| 422 | `validation_error` | Show field message(s); highlight the bad input; keep previous valid view | No |
| 5xx / network | — | “Mission intelligence is unavailable”; keep previous data | Yes, max 3, exponential backoff 1 s / 2 s / 4 s |
| Timeout | — | Same as network | Yes |

Rules:

- Never retry `404` or `422` automatically.
- On `409`, refresh the displayed record instead of repeating the request.
- On a partial screen failure, keep previously loaded data and show a non-blocking
  error banner; do not blank the whole screen.
- The warning strip and the error banner are different components. An error sets
  `data_warnings` to `[]`; never merge the two.

### 6.3 What “success with warnings” means

A `200` with warnings is **not** a green or safe result. The warning strip must
remain visible for the current view. Screens may not collapse warnings into a
toast that disappears.

---

## 7. Field reference for typed clients

| Type | Shape |
| --- | --- |
| `CrewProfileSummary` | `crew_id`, `display_name`, `role`, `sleep_target_hours` |
| `FatigueSignal` | `level`, `source`, `contributing_factors: unknown[]` |
| `SleepSummary` | `sleep_id`, `start_time`, `end_time`, `interruptions`, `quality`, `duration_minutes` |
| `PlannedSleepWindow` | `start_time`, `end_time`, `source`, `duration_minutes` |
| `TaskView` | `task_id`, `astronaut_id`, `name`, `category`, `start_time`, `end_time`, `priority`, `workload_level`, `required_alertness`, `status`, `is_critical`, `duration_minutes` |
| `SuitabilityResult` | `task_id`, `astronaut_id`, `status`, `reasons[]`, `rule_ids[]`, `inputs_used` |
| `Conflict` | `conflict_id`, `rule_id`, `conflict_type`, `severity`, `astronaut_id`, `task_ids[]`, `affected_start`, `affected_end`, `explanation`, `suggested_action`, `source_ids[]`, `config_keys[]`, `task_id` |
| `Recommendation` | `recommendation_id`, `recommendation_type`, `related_conflict_id`, `astronaut_id`, `countermeasure_id`, `countermeasure_name`, `rule_id`, `reason`, `suggested_action`, `expected_benefit`, `priority`, `explanation`, `source_ids[]`, `preconditions[]`, `warnings[]`, `requires_mission_approval`, `requires_medical_review`, `advisory_text` |
| `ScenarioComparison` | `original_metrics`, `proposed_metrics`, `conflict_count_delta`, `resolved_conflicts[]`, `new_conflicts[]`, `summary`, `note`, `config_keys[]` |
| `ScheduleMetrics` | `evaluation_start`, `evaluation_end`, `conflicts_by_type[]`, `total_conflicts`, `highest_severity`, `workload_windows[]`, `total_free_minutes`, `total_recovery_minutes`, `total_recovery_and_free_minutes`, `longest_recovery_gap_minutes`, `tasks_inside_sleep_windows`, `task_ids_inside_sleep_windows[]`, `fatigue_level`, `fatigue_source`, `data_warning_count`, `data_warning_rule_ids[]` |
| `FollowUpRead` | `follow_up_id`, `crew_id`, `recommendation_id`, `related_conflict_id`, `countermeasure_id`, `countermeasure_name`, `rule_id`, `status`, `requires_mission_approval`, `requires_medical_review`, `approved`, `due_at`, `result`, `advisory_text`, `created_at`, `updated_at` |
| `DataWarning` | `code`, `message`, `rule_id`, `task_id` |

`highest_severity` is `null` when there are no conflicts. `approved`, `due_at`,
and `result` are nullable.

---

## 8. Known gaps Person 1 must not work around by inventing data

| Gap | Consequence |
| --- | --- |
| No `GET /follow-ups` | Follow-up list is session-only from create/patch responses |
| No numeric fatigue score | Show categorical level only |
| No task status column | Every task is `planned` |
| Start-only task loading | Tasks overlapping into the window are not returned |
| No crew-local clock | All times UTC; no per-crew offset |
| Process-local follow-ups | Restart clears records |
| No single-item endpoints | Filter the list responses client-side |
| No countermeasure catalogue endpoint | Use id + name from the recommendation |

If a screen needs data outside this list, request a contract change from
Person 4; do not compute it in the UI.

---

## 9. Person 1 acceptance checklist

- [ ] Calls only the seven endpoints in §2.
- [ ] Sends explicit UTC windows for scenario data.
- [ ] Sends the same window on follow-up create as the one that produced the
      recommendation.
- [ ] Renders `data_warnings` on every screen and keeps them visible.
- [ ] Implements loading, empty, error, and unknown-data states separately.
- [ ] Handles all seven error codes in §6.2.
- [ ] Never retries `404`/`422`; retries network/5xx with backoff.
- [ ] Caches per crew + window + endpoint; cancels stale requests.
- [ ] Shows the exact what-if `note` and never calls the delta a fatigue
      improvement.
- [ ] Does not synthesize a fatigue score, task status, follow-up list, or time
      zone.
- [ ] Uses icon + text, not colour alone, for all severities and statuses.
