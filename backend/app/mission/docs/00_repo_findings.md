# Phase 0 — Repository findings

Exploration only. No application code, models, schemas, routers, services, or tests were
modified. The only file created is this report.

Scope: `backend/` of `C:\Users\DELL 7520\Chrono-Guard`, read on 2026-11-13.

---

## a) Python version and installed libraries

- Interpreter: **Python 3.13.3** (`py -0p` lists only 3.13 as installed).
- There is **no virtual environment** in the repository (`no pyvenv.cfg` anywhere), and the
  packages from `backend/requirements.txt` are **not installed** in the active interpreter.

`backend/requirements.txt` pins:

| Package | Pinned | Installed in active interpreter |
| --- | --- | --- |
| fastapi | 0.115.5 | 0.162.2 |
| uvicorn[standard] | 0.32.0 | 0.52.2 |
| sqlmodel | 0.0.22 | **not installed** |
| pydantic-settings | 2.6.1 | 2.16.2 |
| pytest | 8.3.3 | 9.2.0 |
| httpx | 0.27.2 | 0.28.1 |

Other relevant observations:

- **Pydantic is v2**: active version 2.14.3. The code is v2-only
  (`payload.model_dump(exclude_unset=True)`, `ConfigDict`, `model_validator(mode="after")`).
- SQLModel is pinned at 0.0.22 (a Pydantic v2 release) but is absent, so SQLAlchemy is absent too.
- Pydantic is not pinned directly in `requirements.txt`; it arrives transitively via SQLModel /
  FastAPI.
- FastAPI 0.162.2 is present globally but is newer than the pinned 0.115.5, so the active
  environment does **not** match `requirements.txt`.

## b) `history_service.py` function signatures

File: `backend/app/services/history_service.py`

```python
def get_crew(session: Session, crew_id: str) -> CrewProfile | None: ...          # line 16

def get_measurements(
    session: Session,
    crew_id: str,
    types: list[MeasurementType] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
    limit: int | None = None,
) -> list[HealthMeasurement]: ...                                                # lines 21-29

def get_sleep_records(
    session: Session,
    crew_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
) -> list[SleepRecord]: ...                                                      # lines 46-52

def get_upcoming_tasks(
    session: Session,
    crew_id: str,
    from_time: datetime | None = None,
    horizon_hours: int = 72,
) -> list[MissionTask]: ...                                                      # lines 65-70

def get_latest_assessment(session: Session, crew_id: str) -> Assessment | None: ...  # line 86

def get_assessments(
    session: Session, crew_id: str, limit: int, offset: int
) -> list[Assessment]: ...                                                       # lines 97-99
```

Semantics worth noting:

- `get_measurements` and `get_sleep_records` return **newest first** and convert `since`/`until`
  with `to_utc`. `get_sleep_records` filters on `sleep_start`.
- `get_upcoming_tasks` defaults the lower bound to `utcnow()` and the horizon to 72 hours, and
  returns **earliest first**.
- `get_assessments` is offset/limit paged, newest first.
- There is no helper that returns **all** tasks for overlap/conflict detection; only the
  upcoming-window helper exists.

## c) Exact model fields (types, defaults, nullability)

All tables use SQLModel (`SQLModel, table=True`). Datetimes use the custom `UTCDateTime` type
(naive UTC in storage, timezone-aware UTC on read). `new_id` = `uuid4().hex`.

### `MissionTask` — `backend/app/models/mission.py` (lines 14-29)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | `default_factory=new_id` | no (PK) |
| `crew_id` | `str` | — (required), FK `crewprofile.id` | no |
| `title` | `str` | — (required) | no |
| `task_type` | `TaskType` (SA Enum `task_type`) | `TaskType.other` | no |
| `start_time` | `datetime` (`UTCDateTime`) | — (required) | no |
| `end_time` | `datetime` (`UTCDateTime`) | — (required) | no |
| `workload_level` | `WorkloadLevel` (SA Enum `workload_level`) | `WorkloadLevel.medium` | no |
| `is_critical` | `bool` | `False` | no |
| `notes` | `str \| None` | `None` | yes |

Index: `ix_mission_crew_start` on `(crew_id, start_time)`.

### `Assessment` — `backend/app/models/assessment.py` (lines 13-26)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | `default_factory=new_id` | no (PK) |
| `crew_id` | `str` | — (required), FK `crewprofile.id` | no |
| `checkin_id` | `str \| None` | `None`, FK `checkin.id` | yes |
| `status` | `AssessmentStatus` (SA Enum `assessment_status`) | — (required) | no |
| `summary` | `str` | — (required) | no |
| `explanation` | `str` | — (required) | no |
| `contributing_factors` | `list[dict]` (`JSON`) | `default_factory=list` | no |
| `engine_version` | `str` | — (required) | no |
| `created_at` | `datetime` (`UTCDateTime`) | `default_factory=utcnow` | no |

Index: `ix_assessment_crew_created` on `(crew_id, created_at)`.

### `SleepRecord` — `backend/app/models/checkin.py` (lines 44-59)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | `default_factory=new_id` | no (PK) |
| `crew_id` | `str` | — (required), FK `crewprofile.id` | no |
| `checkin_id` | `str \| None` | `None`, FK `checkin.id` | yes |
| `sleep_start` | `datetime` (`UTCDateTime`) | — (required) | no |
| `sleep_end` | `datetime` (`UTCDateTime`) | — (required) | no |
| `duration_hours` | `float` | — (required, computed server-side) | no |
| `interruptions` | `int` | `0` | no |
| `source` | `MeasurementSource` (SA Enum `measurement_source`) | `MeasurementSource.manual` | no |
| `quality` | `QualityFlag` (SA Enum `quality_flag`) | `QualityFlag.valid` | no |

Index: `ix_sleep_crew_start` on `(crew_id, sleep_start)`.

### `HealthMeasurement` — `backend/app/models/checkin.py` (lines 26-41)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | `default_factory=new_id` | no (PK) |
| `crew_id` | `str` | — (required), FK `crewprofile.id` | no |
| `checkin_id` | `str \| None` | `None`, FK `checkin.id` | yes |
| `type` | `MeasurementType` (SA Enum `measurement_type`) | — (required) | no |
| `value` | `float` | — (required) | no |
| `unit` | `str` | — (required, server-owned via `unit_for`) | no |
| `recorded_at` | `datetime` (`UTCDateTime`) | `default_factory=utcnow` | no |
| `source` | `MeasurementSource` (SA Enum) | `MeasurementSource.manual` | no |
| `quality` | `QualityFlag` (SA Enum) | `QualityFlag.valid` | no |

Index: `ix_measurement_crew_recorded` on `(crew_id, recorded_at)`.

### `CrewProfile` — `backend/app/models/crew.py` (lines 8-15)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | `default_factory=new_id` | no (PK) |
| `display_name` | `str` | — (required) | no |
| `role` | `str` | — (required) | no |
| `sleep_target_hours` | `float` | `7.5` | no |
| `created_at` | `datetime` (`UTCDateTime`) | `default_factory=utcnow` | no |

### `Countermeasure` — `backend/app/models/guidance.py` (lines 13-23)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | — (required; slug, not a UUID) | no (PK) |
| `name` | `str` | — (required) | no |
| `preconditions` | `list[dict]` (`JSON`) | `default_factory=list` | no |
| `evidence_status` | `str` | — (required) | no |
| `evidence_source` | `str \| None` | `None` | yes |
| `warnings` | `str \| None` | `None` | yes |
| `requires_mission_approval` | `bool` | `False` | no |
| `follow_up_instruction` | `str \| None` | `None` | yes |

### `ActionHistory` — `backend/app/models/guidance.py` (lines 26-39)

| Field | Type | Default | Nullable |
| --- | --- | --- | --- |
| `id` | `str` | `default_factory=new_id` | no (PK) |
| `crew_id` | `str` | — (required), FK `crewprofile.id` | no |
| `assessment_id` | `str \| None` | `None`, FK `assessment.id` | yes |
| `countermeasure_id` | `str` | — (required), FK `countermeasure.id` | no |
| `status` | `ActionStatus` (SA Enum `action_status`) | `ActionStatus.suggested` | no |
| `follow_up_due_at` | `datetime \| None` (`UTCDateTime`) | `None` | yes |
| `follow_up_result` | `str \| None` | `None` | yes |
| `created_at` | `datetime` (`UTCDateTime`) | `default_factory=utcnow` | no |
| `updated_at` | `datetime` (`UTCDateTime`) | `default_factory=utcnow` | no |

Index: `ix_action_crew_created` on `(crew_id, created_at)`. Note: `updated_at` has **no**
`onupdate` hook, so it is only set on insert unless a caller assigns it.

### Enum values (relevant)

- `TaskType`: `eva`, `maintenance`, `science`, `exercise`, `medical`, `rest`, `other`
- `WorkloadLevel`: `low`, `medium`, `high`
- `AssessmentStatus`: `insufficient_data`, `no_flag`, `monitor`, `elevated_concern`
- `ActionStatus`: `suggested`, `accepted`, `skipped`, `completed`
- `MeasurementType`: `heart_rate`, `systolic_bp`, `diastolic_bp`, `body_temperature`, `mood`,
  `sleepiness_kss`, `perceived_stress`
- `MeasurementSource`: `simulated`, `manual`, `device_import`
- `QualityFlag`: `valid`, `questionable`, `missing`

## d) Demo scenarios and the `MissionTask` rows they create

File: `backend/app/seed/demo_data.py`. Entry points: `python -m app.seed.demo_data`
(all three) or `--scenario <name> [--reset]`, plus `POST /api/v1/demo/seed?scenario=...`
(dev only). Randomness is deterministic per scenario: `random.Random(f"42:{scenario}")`.
Timestamps are relative to `utcnow()` at seed time and clamped to `now - 5 minutes`.
Seeded measurements/sleep use `source="simulated"`. **No scenario seeds any `Assessment` row.**

| Scenario | Crew id | Name / role / sleep target | Check-ins | MissionTask rows |
| --- | --- | --- | --- | --- |
| `normal_routine` | `crew-demo-01` | Luna Park / Flight Engineer / 8.0 h | 7, one per day for the last 7 days at 07:00; sleep 7.2-8.2 h, 0 interruptions; HR 58-70; BP 112-124/70-80; temp 36.3-36.8; mood 4-5; KSS 1-3; stress 1-2 | 14: for each of days 6..0, `Science sample analysis` (`science`, 09:00, 2 h, `low`) and `Resistance exercise` (`exercise`, 16:00, 1 h, `medium`) |
| `reduced_recovery` | `crew-demo-02` | Ivan Volkov / Mission Specialist / 7.5 h | 7, one per day for the last 7 days at 07:00; sleep 2.8 h on day 3, otherwise 4.0-5.5 h, 0 interruptions; HR 72-86; BP 118-132/76-86; temp 36.4-37.2; mood 2-3; KSS 5-8; stress 3-4 | 8: for each of days 6..0, `Maintenance rotation` (`maintenance`, 09:00, 4 h) with workload `low` on days 6-4, `medium` on days 3-2, `high` on days 1-0; plus `Critical EVA - regolith survey` (`eva`, tomorrow 08:00, 4 h, `high`, `is_critical=True`) |
| `incomplete_records` | `crew-demo-03` | Aria Chen / Commander / 7.5 h | 3 only: day-6 08:00 HR 64-72 (notes "Partial entry", no sleep); day-4 21:00 HR 125 + temp 38.3 + sleep 5.0 h; day-1 07:00 mood 3 + KSS 7 (notes "No device sync", no sleep) | 2: `Medical check` (`medical`, 2 days ago 10:00, 1 h, `low`) and `Rest period` (`rest`, today 13:00, 2 h, `low`) |

Notes:

- The `normal_routine` and `reduced_recovery` tasks have `notes=None`; none of the seeded tasks
  set `notes`.
- Task rows are inserted through the private helper `_add_task`, which constructs
  `MissionTask` directly and **bypasses `mission_service.py`**.
- `--reset` deletes only the fixed demo crew ids and their dependent rows in `DELETE_ORDER`
  (`ActionHistory`, `Assessment`, `SleepRecord`, `HealthMeasurement`, `CheckIn`, `MissionTask`).

## e) How to run tests and current result

Documented command (`backend/README.md`, section 4, lines 187-199):

```powershell
cd backend
pytest
```

Actual run on 2026-11-13 from `backend/` (active Python 3.13.3):

```text
pytest : ImportError while loading conftest 'C:\Users\DELL 7520\Chrono-Guard\backend\tests\conftest.py'.
...
tests\conftest.py:7: in <module>
    from sqlmodel import Session, SQLModel
E   ModuleNotFoundError: No module named 'sqlmodel'
```

**The tests do not currently pass — they cannot even be collected** because SQLModel (and
therefore SQLAlchemy) is not installed in the active interpreter, and there is no project
virtualenv. This is an environment/dependency issue, not yet evidence of a code defect. The
pinned versions in `requirements.txt` are also not the versions present globally.

Recommended (not executed, pending approval because it creates files outside this report):
create `backend/.venv`, install `requirements.txt`, and re-run `pytest` from `backend/`.

## f) Where conflict checking could be injected in `mission_service.py`

File: `backend/app/services/mission_service.py`

### `create_task` (lines 14-32)

```text
14  def create_task(session, crew_id, payload) -> MissionTask:
16      start = to_utc(payload.start_time)
17      end = to_utc(payload.end_time)
18      if end <= start:            # only existing window validation
19          raise ValidationFailure(...)
20      task = MissionTask(...)     # row built here
30      session.add(task)
31      session.commit()
```

- Existing checks: only `end_time > start_time` (lines 18-19).
- **Injection point: between lines 19 and 20** — after the window is known to be valid and
  before the row is built, calling e.g.
  `check_conflicts(session, crew_id, start, end, exclude_task_id=None)`.
- If the check must see the new row, it can alternatively run after `session.add(task)` (line 30)
  but before `session.commit()` (line 31); however, checking before line 20 avoids constructing
  an invalid object.
- The function commits internally (line 31), so the check must either run against committed
  state before the commit or use the same session/flush.

### `update_task` (lines 62-77)

```text
62  def update_task(session, task, payload) -> MissionTask:
66      changes = payload.model_dump(exclude_unset=True)
67      start = to_utc(changes.get("start_time", task.start_time))
68      end = to_utc(changes.get("end_time", task.end_time))
69      if end <= start:
70          raise ValidationFailure(...)
71      for field, value in changes.items():
72          setattr(task, field, value)
75      session.add(task)
76      session.commit()
```

- **Injection point: between lines 70 and 71** — after the merged window is validated, before
  `setattr` mutates the ORM object. Pass `exclude_task_id=task.id` so the task does not conflict
  with itself.
- Because fields are applied in a loop, any check that needs the final `task_type` /
  `workload_level` should read `changes` (or the merged values) rather than only `task`.

### Creation/update paths and call sites

- API create: `backend/app/routers/missions.py` line 30 calls `mission_service.create_task`.
- API update: `backend/app/routers/missions.py` line 69 calls `mission_service.update_task`.
- API delete: line 80 calls `mission_service.delete_task` (no conflict logic).
- These are the **only API write paths** for `MissionTask`.
- Seed data bypasses the service entirely via `demo_data._add_task` (lines 89-110), so a
  service-level check will not cover seeded rows. A dedicated conflict-check module could be
  reused by the seed path if desired.
- There is currently no overlap query anywhere: `list_tasks` (lines 35-51) filters by crew and
  optional time window but returns tasks; nothing compares intervals.
- Note: `create_task` and `update_task` commit inside the service, which limits a later
  "check after flush" approach; a pure in-memory/query check before mutation is simplest.

## g) What `Assessment.contributing_factors` JSON looks like

- **No formal contract exists.** The column is `list[dict]` (`app/models/assessment.py` line 24)
  and the read schema is `list[dict[str, Any]]` (`app/schemas/assessment.py` line 22). No keys,
  types, validators, or documentation define the dict shape.
- The only concrete example in the repository is a test fixture,
  `backend/tests/test_checkins.py` lines 108-115:

```python
contributing_factors=[
    {
        "indicator": "sleepiness_kss",
        "observed": 6,
        "reference": "1-9",
        "note": "self reported",
    }
]
```

  Keys observed: `indicator` (str), `observed` (number), `reference` (str), `note` (str).
- `backend/README.md` line 76 only labels the column "JSON"; it does not describe the shape.
- Elsewhere the field is passed through untouched (persisted by `checkin_service._run_engine`
  lines 92-98 and serialised by `AssessmentRead`).

Conclusion: the JSON shape is **undefined anywhere in code or docs**; the four keys above are
only one test's convention and must not be treated as a stable interface without agreement.

## h) Gaps versus my needs (list only — no fixes)

Compared with what the mission-intelligence work needs, the existing models lack:

1. **Task priority** — `MissionTask` has only `workload_level` (low/medium/high) and the boolean
   `is_critical`; there is no ordinal/named priority field (e.g. P1-P5, must-do/should-do).
2. **Required alertness** — no field expressing the alertness demanded by a task (e.g. minimum
   alertness level, vigilance requirement), on `MissionTask` or anywhere else.
3. **Task status** — `MissionTask` has no lifecycle status (planned / in progress / completed /
   cancelled / deferred). `ActionStatus` exists only for countermeasure actions.
4. **Planned sleep periods** — `SleepRecord` stores *actual* sleep tied to a check-in
   (`checkin_id` FK, non-null `sleep_start`/`sleep_end`/`duration_hours`); there is no model for
   planned/future sleep windows, and `TaskType` has no sleep category. A `rest` task is the only
   approximation.
5. **Numeric fatigue score** — `Assessment` has categorical `status` plus free-text
   `summary`/`explanation` and untyped `contributing_factors`; no numeric fatigue score/severity
   field exists in any model.
6. **`Sleep` and `Communication` task types** — `TaskType` contains `eva`, `maintenance`,
   `science`, `exercise`, `medical`, `rest`, `other`; it has neither `sleep` nor `communication`
   (nor a sleep-like category beyond `rest`).

## i) How routers are registered in `app/routers/__init__.py`

File: `backend/app/routers/__init__.py` (12 lines)

```python
from app.routers import assessments, checkins, crew, demo, history, missions

ROUTERS = [
    crew.router,
    checkins.router,
    history.router,
    missions.router,
    assessments.router,
    demo.router,
]
```

Pattern:

1. Each router module defines a module-level `router = APIRouter(tags=[...])`
   (e.g. `missions.py` line 18: `router = APIRouter(tags=["missions"])`) and declares full paths
   including the `/crew/{crew_id}/...` segment; no per-router prefix is used.
2. `app/main.py` iterates the list and includes every router under the shared prefix
   (lines 52-53):

   ```python
   for router in ROUTERS:
       app.include_router(router, prefix="/api/v1")
   ```

3. To register a new router, two edits are needed in `app/routers/__init__.py`: add the module
   to the `from app.routers import ...` line and append `<module>.router` to `ROUTERS`.
   This file is **outside `backend/app/mission/`**, so per `AGENTS.md` it requires explicit
   approval before editing.

---

## Summary of blockers/risks found

- **Tests cannot run** until `sqlmodel`/`sqlalchemy` (and ideally pinned FastAPI/pytest/httpx)
  are installed in an isolated environment.
- `MissionTask` has no overlap/conflict logic; the only validation is `end_time > start_time`.
- `contributing_factors` has no defined schema; only a test fixture shows an unofficial shape.
- All six model gaps in section (h) are currently unimplemented.
- Two permitted out-of-folder edits (router registration, `mission_service` injection) are
  identified but not performed.

---

## Environment baseline (supersedes the blocker in section e)

Created on 2026-11-13 with the installed Python 3.13.3, after confirming that the root
`.gitignore` already ignores `.venv/` (no `.gitignore` edit was made).
`backend/requirements.txt` was **not modified**.

### Commands used (Windows PowerShell, run from `backend/`)

```powershell
# 1. Create the isolated environment
python -m venv .venv

# 2. Install the pinned requirements into that environment
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

# 3. Check installed versions
& ".\.venv\Scripts\python.exe" -c "from importlib.metadata import version; [print(n, version(n)) for n in ('fastapi','sqlmodel','pydantic','pytest','sqlalchemy','httpx','pydantic-settings','uvicorn')]"

# 4. Run the test suite with the venv interpreter (not the global one)
& ".\.venv\Scripts\python.exe" -m pytest -v
```

### Installed versions (venv)

| Package | Version |
| --- | --- |
| Python | 3.13.3 |
| fastapi | 0.115.5 |
| sqlmodel | 0.0.22 |
| pydantic | 2.14.3 (v2) |
| pytest | 8.3.3 |
| sqlalchemy | 2.0.57 |
| httpx | 0.27.2 |
| pydantic-settings | 2.6.1 |
| uvicorn | 0.32.0 |

(Pydantic remains v2, matching the v2-only code. SQLAlchemy 2.0.57 is resolved by SQLModel
0.0.22, not pinned directly.)

### Pytest result

```text
platform win32 -- Python 3.13.3, pytest-8.3.3, pluggy-1.7.0
rootdir: C:\Users\DELL 7520\Chrono-Guard\backend
collected 16 items
16 passed, 1 warning in 2.05s
```

The single warning is a third-party `DeprecationWarning` from
`starlette/testclient.py` about the `anyio.abc.BlockingPortal` alias; it is unrelated to
application code. **Baseline: all 16 existing tests pass.**
