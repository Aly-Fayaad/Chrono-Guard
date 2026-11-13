# Lunar Crew Health Companion — Backend

Synthetic-data backend for astronaut health check-ins, trends, mission tasks, and
read-only assessments. FastAPI + SQLModel + SQLite, with plug-in hooks for the AI
and guidance modules.

## 1. File tree

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # create_app, CORS, lifespan, router registration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Settings: DATABASE_URL, CORS_ORIGINS, ENV, ANALYSIS_ENGINE
│   │   └── database.py          # engine, UTCDateTime, init_db, get_session
│   ├── models/
│   │   ├── __init__.py          # imports every model
│   │   ├── enums.py
│   │   ├── crew.py              # CrewProfile
│   │   ├── checkin.py           # CheckIn, HealthMeasurement, SleepRecord
│   │   ├── mission.py           # MissionTask
│   │   ├── assessment.py        # Assessment
│   │   └── guidance.py          # Countermeasure, ActionHistory
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── crew.py
│   │   ├── checkin.py
│   │   ├── history.py
│   │   ├── mission.py
│   │   └── assessment.py
│   ├── routers/
│   │   ├── __init__.py          # ROUTERS = [...]
│   │   ├── crew.py
│   │   ├── checkins.py
│   │   ├── history.py
│   │   ├── missions.py
│   │   ├── assessments.py
│   │   └── demo.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── validation.py        # all hard/soft limits
│   │   ├── checkin_service.py
│   │   ├── history_service.py   # P3/P4 data-access contract
│   │   ├── mission_service.py
│   │   └── analysis.py          # AnalysisEngine, NullEngine, load_engine
│   ├── ml/__init__.py           # reserved for Person 3
│   ├── mission/__init__.py      # reserved for Person 4
│   └── seed/
│       ├── __init__.py
│       └── demo_data.py         # 3 scenarios + CLI
├── tests/
│   ├── conftest.py
│   ├── test_checkins.py
│   ├── test_history.py
│   └── test_missions.py
├── requirements.txt
├── .env.example
└── README.md
```

## 2. Database schema

SQLite is the default. All primary keys are strings (`uuid4().hex`) except the
demo crews and countermeasure slugs. All datetimes are stored as UTC and returned
timezone-aware. Enum columns store their string values.

| Table | Columns | Foreign keys |
| --- | --- | --- |
| `crewprofile` | `id` PK, `display_name`, `role`, `sleep_target_hours` (default 7.5), `created_at` | — |
| `checkin` | `id` PK, `crew_id`, `submitted_at`, `notes` | `crew_id → crewprofile.id` |
| `healthmeasurement` | `id` PK, `crew_id`, `checkin_id`, `type`, `value`, `unit`, `recorded_at`, `source`, `quality` | `crew_id → crewprofile.id`, `checkin_id → checkin.id` (nullable) |
| `sleeprecord` | `id` PK, `crew_id`, `checkin_id`, `sleep_start`, `sleep_end`, `duration_hours`, `interruptions`, `source`, `quality` | `crew_id → crewprofile.id`, `checkin_id → checkin.id` (nullable) |
| `missiontask` | `id` PK, `crew_id`, `title`, `task_type`, `start_time`, `end_time`, `workload_level`, `is_critical`, `notes` | `crew_id → crewprofile.id` |
| `assessment` | `id` PK, `crew_id`, `checkin_id`, `status`, `summary`, `explanation`, `contributing_factors` JSON, `engine_version`, `created_at` | `crew_id → crewprofile.id`, `checkin_id → checkin.id` (nullable) |
| `countermeasure` | `id` PK (slug), `name`, `preconditions` JSON, `evidence_status`, `evidence_source`, `warnings`, `requires_mission_approval`, `follow_up_instruction` | — |
| `actionhistory` | `id` PK, `crew_id`, `assessment_id`, `countermeasure_id`, `status`, `follow_up_due_at`, `follow_up_result`, `created_at`, `updated_at` | `crew_id → crewprofile.id`, `assessment_id → assessment.id` (nullable), `countermeasure_id → countermeasure.id` |

Composite indexes: `checkin(crew_id, submitted_at)`,
`healthmeasurement(crew_id, recorded_at)`, `sleeprecord(crew_id, sleep_start)`,
`missiontask(crew_id, start_time)`, `assessment(crew_id, created_at)`,
`actionhistory(crew_id, created_at)`.

Enum values:

- Measurement type: `heart_rate`, `systolic_bp`, `diastolic_bp`, `body_temperature`, `mood`, `sleepiness_kss`, `perceived_stress`
- Source: `simulated`, `manual`, `device_import`
- Quality: `valid`, `questionable`, `missing`
- Task type: `eva`, `maintenance`, `science`, `exercise`, `medical`, `rest`, `other`
- Workload: `low`, `medium`, `high`
- Assessment status: `insufficient_data`, `no_flag`, `monitor`, `elevated_concern`
- Action status: `suggested`, `accepted`, `skipped`, `completed`

## 3. Endpoints

All API routes use the `/api/v1` prefix. `/health` is also exposed at the root for
infrastructure probes. Unknown crew/record → `404`; validation failure → `422`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health`, `/api/v1/health` | Liveness + active environment |
| GET | `/api/v1/crew` | List crew profiles |
| GET | `/api/v1/crew/{crew_id}` | Read one crew profile |
| PATCH | `/api/v1/crew/{crew_id}` | Update `display_name`, `role`, `sleep_target_hours` |
| POST | `/api/v1/crew/{crew_id}/checkins` | Validate + atomically save a check-in, then run the analysis hook |
| GET | `/api/v1/crew/{crew_id}/checkins` | List check-ins (`limit` 1–200, default 50; `offset`) |
| GET | `/api/v1/crew/{crew_id}/checkins/{checkin_id}` | Read one check-in with measurements, sleep, assessment |
| GET | `/api/v1/crew/{crew_id}/history/measurements` | Measurement history (`type`, `from`, `to`, `limit`) |
| GET | `/api/v1/crew/{crew_id}/history/sleep` | Sleep history (`from`, `to`, `limit`) |
| POST | `/api/v1/crew/{crew_id}/missions` | Create a mission task |
| GET | `/api/v1/crew/{crew_id}/missions` | List tasks (`upcoming`, `from`, `to`) |
| GET | `/api/v1/crew/{crew_id}/missions/{task_id}` | Read one task |
| PATCH | `/api/v1/crew/{crew_id}/missions/{task_id}` | Partial task update |
| DELETE | `/api/v1/crew/{crew_id}/missions/{task_id}` | Delete a task |
| GET | `/api/v1/crew/{crew_id}/assessments` | Read-only assessment list (`limit`, `offset`) |
| GET | `/api/v1/crew/{crew_id}/assessments/latest` | Latest assessment (`404` when none) |
| POST | `/api/v1/demo/seed?scenario=...` | Seed one demo scenario (`ENV=dev` only) |

### Check-in contract

```json
{
  "recorded_at": "2026-11-13T22:00:00Z",
  "sleep": {"sleep_start": "...", "sleep_end": "...", "interruptions": 1},
  "behavioral": {"mood": 3, "sleepiness_kss": 6, "perceived_stress": 2},
  "cardiovascular": {"heart_rate": 72, "systolic_bp": 118, "diastolic_bp": 76},
  "physical": {"body_temperature": 36.7},
  "notes": null
}
```

Response:

```json
{
  "checkin": {"id": "...", "crew_id": "...", "submitted_at": "...", "notes": null},
  "measurements": [{"type": "heart_rate", "value": 72, "unit": "bpm", "quality": "valid", "...": "..."}],
  "sleep_record": {"duration_hours": 7.5, "quality": "valid", "...": "..."},
  "assessment": null
}
```

The client never sends units or quality. `source` defaults to `manual`, units come
from the server-side map, and `duration_hours` is computed from the sleep window.

### Person 3 hook

Set `ANALYSIS_ENGINE` to a `module:Class` path. The class must implement:

```python
def analyze(self, session, crew_id: str, checkin_id: str | None) -> Assessment | None
```

The engine is called **after** the check-in commit. If it raises or returns `None`,
the check-in is still saved and `assessment` is `null`. A returned unsaved
`Assessment` is persisted and included in the response.

### Person 4 hook

`app/models/guidance.py` contains the `Countermeasure` and `ActionHistory` tables.
`app/services/history_service.py` exposes the agreed read helpers:
`get_crew`, `get_measurements`, `get_sleep_records`, `get_upcoming_tasks`,
`get_latest_assessment`.

## 4. Run commands

```bash
cd backend

# create and activate a virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell
# source .venv/bin/activate         # macOS / Linux

pip install -r requirements.txt

# optional local configuration
copy .env.example .env              # PowerShell
# cp .env.example .env              # macOS / Linux

uvicorn app.main:app --reload
```

OpenAPI docs: <http://127.0.0.1:8000/docs>

```bash
# seed all three scenarios (skips existing demo crews)
python -m app.seed.demo_data

# seed one scenario and replace its data
python -m app.seed.demo_data --scenario reduced_recovery --reset

# alternative: HTTP seed endpoint while ENV=dev
curl -X POST "http://127.0.0.1:8000/api/v1/demo/seed?scenario=normal_routine"

# tests
pytest
```

## 5. Assumptions

- `submitted_at` is the server time of submission; `recorded_at` is taken from the
  request (defaulting to now) and stored on measurements. Sleep is filtered by
  `sleep_start`.
- A check-in must contain at least one health or sleep value; notes alone are
  rejected with `422`.
- Naive datetimes are treated as UTC. All responses are UTC.
- Scale measurements (`mood`, `sleepiness_kss`, `perceived_stress`) use unit
  `score`; temperature uses `C`, blood pressure `mmHg`, heart rate `bpm`, sleep
  duration `h`.
- Hard-bound violations are rejected with `422`; soft-bound violations are saved
  with `quality="questionable"`. Limits are prototype plausibility ranges, not
  clinical thresholds.
- `GET .../assessments/latest` returns `404` if the crew has no assessments.
- Mission deletion returns `200 {"deleted": true, "id": ...}` rather than an empty
  `204`, so every route has a response model.
- `DELETE`/`PATCH` on a task belonging to another crew returns `404`.
- Demo seed data is synthetic, deterministic via a fixed random seed, and uses
  `source="simulated"`. `--reset` removes only the fixed demo crew ids
  (`crew-demo-01` … `crew-demo-03`) and their dependent rows.
- There is no authentication, no offline sync, and no client event-ID idempotency.
- SQLite is the single source of truth. `DATABASE_URL` can point at another
  SQLAlchemy database, but the corresponding driver must be installed separately.
- `CORS_ORIGINS` is a comma-separated string for easy `.env` use.
- `tests/conftest.py` uses an isolated in-memory SQLite database and overrides the
  database dependency; tests never touch the development database.
