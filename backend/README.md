# Lunar Crew Health Companion — Backend

Synthetic-data backend for astronaut health check-ins, trends, mission tasks, and
read-only assessments. FastAPI + SQLModel, PostgreSQL in production (psycopg 3),
with SQLite kept as the code-level test/local fallback. Plug-in hooks remain for
the AI and guidance modules.

The runtime database is selected by `DATABASE_URL`. A plain
`postgresql://…` / `postgres://…` URL is normalised to
`postgresql+psycopg://…`; keep credentials in `backend/.env` (gitignored).

## 1. File tree

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # create_app, CORS, lifespan, health, router registration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Settings: DATABASE_URL, CORS_ORIGINS, ENV, ANALYSIS_ENGINE
│   │   ├── database.py          # engine, UTCDateTime, JSON_DOCUMENT, init_db, get_session
│   │   └── errors.py            # unified 422 detail-list helpers
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
│   │   ├── crew.py              # create/read/update/delete payloads
│   │   ├── checkin.py           # CheckInCreate, CheckInSource, responses
│   │   ├── history.py
│   │   ├── mission.py
│   │   ├── assessment.py
│   │   ├── dashboard.py         # descriptive summary schema
│   │   └── analysis.py          # {"assessment": ...} response
│   ├── routers/
│   │   ├── __init__.py          # ROUTERS = [...]
│   │   ├── crew.py              # POST/GET/PATCH/DELETE crew
│   │   ├── checkins.py
│   │   ├── history.py           # repeated ?type= filters
│   │   ├── missions.py          # filters + X-Total-Count
│   │   ├── assessments.py       # list/latest/detail/reanalyze
│   │   ├── analysis.py          # explicit analysis/run
│   │   ├── dashboard.py         # dashboard/summary
│   │   ├── overview.py
│   │   └── demo.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── validation.py        # all hard/soft limits
│   │   ├── checkin_service.py   # shared persist + run_analysis path
│   │   ├── crew_service.py      # create + transactional cascade delete
│   │   ├── dashboard_service.py # descriptive seven-day aggregation
│   │   ├── history_service.py   # P3/P4 data-access contract
│   │   ├── mission_service.py
│   │   ├── mission_clock.py     # backend-owned MET / D+ / local time
│   │   ├── reanalysis_service.py # additive, idempotent historical replay
│   │   └── analysis.py          # AnalysisEngine, NullEngine, load_engine
│   ├── ml/                      # CrewHealthEngine (vendored crew_health package)
│   ├── mission/                 # mission-intelligence module (router, services, tests)
│   └── seed/
│       ├── __init__.py
│       └── demo_data.py         # 3 scenarios + CLI (--reset, --analyze)
├── crew_health/                 # vendored three-process-model pipeline
├── tests/
│   ├── conftest.py
│   ├── test_checkins.py
│   ├── test_history.py
│   ├── test_missions.py
│   ├── test_overview.py
│   ├── test_reanalysis.py
│   └── test_tier1_api.py        # crew lifecycle, analysis, dashboard, contracts
├── requirements.txt
├── .env.example
└── README.md
```

## 2. Database schema

PostgreSQL is the runtime database (Neon in this deployment); SQLite remains the
fallback for tests and local boot when `DATABASE_URL` is unset. All primary keys
are strings (`uuid4().hex`) except caller-supplied crew slugs and countermeasure
slugs. PostgreSQL uses `TIMESTAMP WITH TIME ZONE`, native enum types, and `JSONB`
for document columns; SQLite uses its compatible fallbacks. Datetimes are always
stored and returned as UTC, timezone-aware in API responses.

Foreign keys declare `ON DELETE CASCADE` for crew-owned rows. `DELETE /crew/{id}`
still deletes child rows explicitly in one transaction, so it also works on
older SQLite schemas that predate the cascades.

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

- Measurement type: `heart_rate`, `hrv`, `systolic_bp`, `diastolic_bp`, `body_temperature`, `mood`, `sleepiness_kss`, `perceived_stress`
- Source: `simulated`, `manual`, `device_import`
- Quality: `valid`, `questionable`, `missing`
- Task type: `eva`, `maintenance`, `science`, `exercise`, `medical`, `rest`, `other`
- Workload: `low`, `medium`, `high`
- Assessment status: `insufficient_data`, `no_flag`, `monitor`, `elevated_concern`
- Action status: `suggested`, `accepted`, `skipped`, `completed`

## 3. Endpoints

All API routes use the `/api/v1` prefix. `/health` is also exposed at the root for
infrastructure probes. Unknown crew/record → `404`; validation failure → `422`.

Every list route keeps its existing array/envelope body and adds an
`X-Total-Count` response header (exposed through CORS). Every `422` uses the
unified `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` shape,
including domain validation and mission-intelligence errors.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health`, `/api/v1/health` | Liveness + active environment |
| GET | `/health/ready`, `/api/v1/health/ready` | Readiness probe with `SELECT 1` database check |
| GET | `/api/v1/crew` | List crew profiles (`X-Total-Count`) |
| POST | `/api/v1/crew` | Create a crew profile; `id`/`slug` optional, `sleep_target_hours` optional |
| GET | `/api/v1/crew/{crew_id}` | Read one crew profile |
| PATCH | `/api/v1/crew/{crew_id}` | Update `display_name`, `role`, `sleep_target_hours` |
| DELETE | `/api/v1/crew/{crew_id}` | Delete a crew and every dependent row in one transaction |
| GET | `/api/v1/crew/{crew_id}/overview` | Unified console payload: mission clock, series, detections, tasks, latest assessment |
| POST | `/api/v1/crew/{crew_id}/checkins` | Validate + atomically save a check-in, then run the analysis hook |
| GET | `/api/v1/crew/{crew_id}/checkins` | List check-ins (`limit` 1–200, default 50; `offset`; `X-Total-Count`) |
| GET | `/api/v1/crew/{crew_id}/checkins/{checkin_id}` | Read one check-in with measurements, sleep, assessment |
| GET | `/api/v1/crew/{crew_id}/history/measurements` | Measurement history (`type` repeatable, `from`, `to`, `limit`; `X-Total-Count`) |
| GET | `/api/v1/crew/{crew_id}/history/sleep` | Sleep history (`from`, `to`, `limit`; `X-Total-Count`) |
| POST | `/api/v1/crew/{crew_id}/missions` | Create a mission task |
| GET | `/api/v1/crew/{crew_id}/missions` | List tasks (`upcoming`, `horizon_hours`, `from`, `to`, `task_type`, `workload_level`, `is_critical`; `X-Total-Count`) |
| GET | `/api/v1/crew/{crew_id}/missions/{task_id}` | Read one task |
| PATCH | `/api/v1/crew/{crew_id}/missions/{task_id}` | Partial task update |
| DELETE | `/api/v1/crew/{crew_id}/missions/{task_id}` | Delete a task |
| GET | `/api/v1/crew/{crew_id}/assessments` | Read-only assessment list (`limit`, `offset`; `X-Total-Count`) |
| GET | `/api/v1/crew/{crew_id}/assessments/latest` | Latest assessment (`404` when none) |
| GET | `/api/v1/crew/{crew_id}/assessments/{assessment_id}` | Assessment detail (`404` when missing or owned by another crew) |
| POST | `/api/v1/crew/{crew_id}/analysis/run?checkin_id=...` | Run the configured engine on a given/latest check-in; `{"assessment": null}` for `NullEngine` or a safely failed engine |
| GET | `/api/v1/crew/{crew_id}/dashboard/summary` | Descriptive per-measurement and sleep summary (no baselines, thresholds, alerts, or scores) |
| POST | `/api/v1/crew/{crew_id}/assessments/reanalyze` | Safe historical re-analysis of all stored check-ins (additive, idempotent) |
| POST | `/api/v1/demo/seed?scenario=...` | Seed one demo scenario (`ENV=dev` only) |

### Check-in contract

```json
{
  "recorded_at": "2026-11-13T22:00:00Z",
  "source": "manual",
  "sleep": {"sleep_start": "...", "sleep_end": "...", "interruptions": 1},
  "behavioral": {"mood": 3, "sleepiness_kss": 6, "perceived_stress": 2},
  "cardiovascular": {"heart_rate": 72, "hrv": 60, "systolic_bp": 118, "diastolic_bp": 76},
  "physical": {"body_temperature": 36.7},
  "notes": null
}
```

`source` is optional and defaults to `manual`. API submissions accept only
`manual` or `device_import`; `simulated` is reserved for server-side demo seeds
and is rejected with `422` if a client sends it.

Response:

```json
{
  "checkin": {"id": "...", "crew_id": "...", "submitted_at": "...", "notes": null},
  "measurements": [{"type": "heart_rate", "value": 72, "unit": "bpm", "quality": "valid", "...": "..."}],
  "sleep_record": {"duration_hours": 7.5, "quality": "valid", "...": "..."},
  "assessment": {"status": "monitor", "summary": "...", "contributing_factors": ["..."]}
}
```

The client never sends units or quality. `source` defaults to `manual`, units come
from the server-side map, and `duration_hours` is computed from the sleep window.

### Mission clock (backend-owned)

The backend is the single source of truth for the mission clock. `GET /overview`
returns a `mission` object; the frontend uses its epoch and `mission_day_hours` to
format labels and advance the ticking display. Apart from a documented first-paint
fallback that matches these defaults, it owns no separate epoch or day-length
constant and does not use a 24 h Earth-day assumption for mission labels.

| Setting | Default | Meaning |
| --- | --- | --- |
| `MISSION_EPOCH` | `2026-10-30T07:00:00Z` | UTC instant of mission day 0, 00:00 mission-local |
| `MISSION_DAY_HOURS` | `24.65` | Operational day length (Martian sol) |

Derived values (`app/services/mission_clock.py`):

```text
MET (h)                 = (now - epoch) / 1 h
mission_day_index       = floor(MET / mission_day_hours)
mission_local_time_hours = MET mod mission_day_hours
met_label               = "D+<day> <local time>"
```

Because the default day length is 24.65 h, the clock does **not** roll over at
24.00 h. For example, 24.4 h after the epoch is still `D+000 24:24`, and the next
day starts at 24.65 h of MET.

**Scientific boundary:** `MISSION_DAY_HOURS=24.65` is an operational mission
convention. It does **not** change the published three-process-model equations,
which remain the 24 h circadian and 12 h ultradian equations from Ingre et al.
(2014). The engine explicitly reports `mission_time.circadian_period_hours == 24.0`,
`ultradian_period_hours == 12.0`, and
`published_circadian_equations_unchanged == true`. Stored sleep windows are kept
on the UTC/Earth clock (`records_on_mission_clock: false`); reinterpreting them on
a 24.65 h dial is not validated, so it is not done.

### Assessment status rules

The status is a **provisional product rule**, not a validated clinical or
operational impairment classification. Every assessment includes a
`status_rule` contributing factor that states the rule and this limitation.

| Rule | Source | Direction / interpretation |
| --- | --- | --- |
| Predicted KSS drives the primary branch | Published group-level three-process model (Ingre et al. 2014) | Higher = sleepier. Residual SD ≈ 1.42 KSS units; not individually calibrated and not validated in microgravity. |
| `predicted KSS >= 6` → `monitor` | KSS instrument anchor (“some signs of sleepiness”) used as a **provisional prototype heuristic** | Not a clinical or operational threshold. |
| `predicted KSS >= 7` **and** (recent persistent deviation **or** high-risk task) → `elevated_concern` | KSS anchor (“sleepy, but no difficulty remaining awake”) plus product combination rule; **provisional heuristic** | The combination is not published or validated. |
| Alertness band is `below_typical` / `much_below_typical` → at least `monitor` | Percentile **within the simulated schedule** (10th / 25th cutoffs); descriptive | Higher percentile = more alert. Not a clinical threshold. |
| Persistent deviation → at least `monitor` | Robust median/MAD baseline, `|z| >= 2` for `>= 2` consecutive nights (statistical heuristic) | Only runs reaching the most recent completed baseline night are considered, so an old resolved run does not keep a crew member flagged. |
| Self-reported KSS | User input, reference only | **Never** used as a model input and never merged with predicted KSS. |

If there are fewer than two sleep nights, the result is `insufficient_data` rather
than a health status. `no_flag` is the default when no rule fires; it means “no
rule triggered”, not “clinically fit for duty”.

### Historical re-analysis

`POST /api/v1/crew/{crew_id}/assessments/reanalyze` walks every stored check-in
for a crew member, oldest first, and runs the configured engine on each one.

Guarantees:

- **Additive** — original check-ins, measurements, and sleep records are never
  modified or deleted.
- **History-preserving** — previous assessments (including older engine
  versions) remain in the assessment list.
- **Idempotent** — a check-in that already has an assessment from the current
  engine version is skipped, so retries do not create duplicates.
- **Failure-isolated** — an exception for one check-in is recorded as `failed`
  and the remaining check-ins continue.
- **Explicit engine state** — returns `503` when no engine is configured and
  `404` for an unknown crew.

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/crew/crew-demo-01/assessments/reanalyze"
```

```json
{
  "crew_id": "crew-demo-01",
  "engine_version": "crew-health 0.2.0 (tpm-ingre2014 + workload-ext; status-rule v1)",
  "processed": 12,
  "succeeded": 11,
  "skipped": 0,
  "failed": 1,
  "insufficient": 2,
  "results": [
    {
      "checkin_id": "…",
      "status": "succeeded",
      "assessment_id": "…",
      "assessment_status": "monitor",
      "reason": null
    }
  ]
}
```

Field meanings:

- `processed` — number of stored check-ins examined.
- `succeeded` — new assessments persisted. Includes `insufficient_data`
  assessments, which are also counted in `insufficient`.
- `skipped` — already analysed with this engine version, or the engine returned
  nothing.
- `failed` — analysis raised; `reason` carries the error and the batch continues.

Inspect results with the existing read routes, for example
`GET /api/v1/crew/{crew_id}/assessments` (newest first) or
`GET /api/v1/crew/{crew_id}/checkins/{checkin_id}` (the check-in plus its
assessment). Re-running after deploying a new engine version analyses the same
check-ins again while keeping the old rows.

Historical runs only use data that existed at each check-in's `as_of` time:
sleep records and self-reported KSS are filtered to check-ins submitted at or
before that moment. Mission-task history has no creation timestamp, so re-analysis
cannot perfectly reconstruct tasks that were added or deleted after the fact.

### Person 3 hook

`ANALYSIS_ENGINE` defaults to `app.ml.crew_health_engine:CrewHealthEngine`; set it
to `app.services.analysis:NullEngine` to run without analysis. Custom engines use
a `module:Class` path and must implement:

```python
version: str  # stable engine identifier, used for idempotent re-analysis

def analyze(self, session, crew_id: str, checkin_id: str | None) -> Assessment | None
```

The engine is called **after** the check-in commit. If it raises or returns `None`,
the check-in is still saved and `assessment` is `null`. A returned unsaved
`Assessment` is persisted and included in the response. Bump `version` whenever
analysis output semantics change; historical re-analysis then creates new rows
for the new version while keeping the previous assessments.

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

# PostgreSQL (recommended for the demo / production)
copy .env.example .env              # PowerShell
# cp .env.example .env              # macOS / Linux
# Edit DATABASE_URL in .env. Plain postgresql:// URLs are accepted.
# Keep credentials out of git; .env is ignored.

# SQLite fallback for local boot without .env
# DATABASE_URL=sqlite:///./chronoguard.db

# Mission clock defaults: MISSION_EPOCH=2026-10-30T07:00:00Z, MISSION_DAY_HOURS=24.65
# (24.65 h is the operational Martian sol; circadian equations stay at 24 h.)
# Set ANALYSIS_ENGINE=app.services.analysis:NullEngine to disable analysis.

uvicorn app.main:app --reload
```

OpenAPI docs: <http://127.0.0.1:8000/docs>

The schema is created on startup (`init_db`). On PostgreSQL it also adds newly
introduced enum members, so a database created before `hrv` existed keeps
working without a manual reset.

```bash
# seed all three scenarios (skips existing demo crews)
python -m app.seed.demo_data

# seed one scenario and replace its data, then analyse every seeded check-in
python -m app.seed.demo_data --scenario reduced_recovery --reset --analyze

# alternative: HTTP seed endpoint while ENV=dev (also runs the analysis engine)
curl -X POST "http://127.0.0.1:8000/api/v1/demo/seed?scenario=normal_routine"

# tests (isolated in-memory SQLite; no PostgreSQL connection)
pytest
```

### PostgreSQL operations

`backend/.env` is loaded relative to `app/core/config.py`, so the API finds it
whether Uvicorn is started from `backend/` or from the repository root.

```dotenv
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
ENV=dev
ANALYSIS_ENGINE=app.ml.crew_health_engine:CrewHealthEngine
```

Startup calls `init_db`, which creates missing tables and adds any new members to
existing PostgreSQL enum types. It does not drop or rewrite existing data. For a
fresh Neon database, start the API once or run the seed CLI; both create the
schema before writing rows.

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
- `GET .../assessments/{assessment_id}` returns `404` when the id is missing or
  belongs to another crew.
- Mission deletion returns `200 {"deleted": true, "id": ...}` rather than an empty
  `204`, so every route has a response model.
- `DELETE`/`PATCH` on a task belonging to another crew returns `404`.
- Demo seed data is synthetic, deterministic via a fixed random seed, and uses
  `source="simulated"`. `--reset` removes only the fixed demo crew ids
  (`crew-demo-01` … `crew-demo-03`) and their dependent rows. `--analyze` runs
  the configured engine on every seeded check-in and prints created/skipped/failed
  counts.
- There is no authentication and no client event-ID idempotency. The frontend is
  online-only and surfaces failed writes immediately; callers should use a
  gateway or an idempotency key before enabling retrying clients.
- PostgreSQL is the runtime database. SQLite is the code-level fallback for tests
  and local boot; `DATABASE_URL` selects the active engine.
- `CORS_ORIGINS` is a comma-separated string for easy `.env` use. `X-Total-Count`
  and `X-Request-ID` are exposed to browser clients.
- `tests/conftest.py` uses an isolated in-memory SQLite database and overrides the
  database dependency; tests never touch the development database.

## 6. Known gaps and team handoff

This backend deliberately stops at the stable contracts. The items below are
missing, stubbed, or intentionally out of scope. Each row names the API or
integration that depends on it and the owner who should add it.

### 6.1 Blocking the full demo

| Missing piece | Current state | Dependent API / integration | Owner |
| --- | --- | --- | --- |
| AI analysis engine | Integrated at `app/ml/crew_health_engine.py` (default `ANALYSIS_ENGINE`) | Check-ins return an assessment once two sleep nights exist; `GET /overview` exposes the latest one | done |
| Assessment seed data | HTTP `POST /demo/seed` runs the engine on the newest seeded check-in | Demo screens display a real engine assessment immediately | done |
| Retroactive / batch analysis | `POST /crew/{id}/assessments/reanalyze` re-runs stored check-ins safely | Old check-ins can be regenerated without touching original records | done |
| Assessment deep-link route | `GET /crew/{id}/assessments/{assessment_id}` is crew-scoped and returns `404` for another crew | Detail screens and deep links can load one assessment | done |
| Guidance API | `Countermeasure` and `ActionHistory` tables exist, but there is no router, schema, or service | Frontend guidance panel has no endpoint; P4 must add and register a router | P4 |
| Countermeasure catalogue seed | No `Countermeasure` rows are seeded | `ActionHistory.countermeasure_id` cannot be populated; P4 must seed the catalogue | P4 |
| Action history API | `ActionHistory` is a table only | Accept / skip / complete actions and follow-up results are not exposed | P4 |
| Mission conflict / overlap logic | Mission-intelligence reads use interval overlap, including tasks already in progress at window start | CRUD remains non-blocking and emits warnings to logs; use mission-intel conflict routes for advisory results | limited |
| Mission approval workflow | `requires_mission_approval` is only a column | No approve/reject endpoint or status transition for P4 guidance | P4 |
| Crew onboarding | `POST /crew` creates a profile; `id`/`slug` and `sleep_target_hours` are optional. `DELETE /crew/{id}` removes all child rows transactionally | Frontend can provision or remove a crew without the seed | done |
| Device import ingestion | `POST /checkins` accepts `source="device_import"` and writes it to measurements and sleep | Device-imported data is distinguishable from manual entry | done |

### 6.2 Frontend integration notes

| Behaviour | Why it matters | Owner |
| --- | --- | --- |
| `422` bodies use one shape | Pydantic and domain errors both return `detail: [{loc, msg, type}]`; the client reads the first message. | done |
| `GET .../assessments/latest` returns `404` when empty | Treat `404` as "no assessment yet", not as a network failure. | P1 |
| `GET .../checkins` returns headers only | Measurements and sleep are in the detail route or history routes; the list is not a full record. | P1 |
| History responses are envelopes | Measurements arrive as `{"measurements": [...]}` and sleep as `{"sleep_records": [...]}`. | P1 |
| History `type` filter is repeatable | `?type=heart_rate&type=mood` combines filters; a single value still works. | done |
| Health data aggregation | `GET /crew/{id}/overview` composes mission clock, series, detections, tasks, and assessment; `dashboard/summary` provides descriptive per-metric and sleep statistics | Frontend no longer needs local aggregation for the console | done |
| Pagination totals | List routes keep their array/envelope bodies and add `X-Total-Count`. | done |
| All timestamps are UTC | The UI must convert to the crew's local display time. | P1 |
| Units are fixed by the server | Display the returned `unit`; the client cannot submit units. | P1 |
| Mission list filters | `task_type`, `workload_level`, `is_critical`, and optional `horizon_hours` with `upcoming=true` are supported. | done |
| Upcoming semantics differ | The HTTP route returns all future tasks without `horizon_hours`; `history_service.get_upcoming_tasks()` keeps its 72-hour default for P3/P4. | documented |
| No API client is generated | `/openapi.json` is available; the frontend mirrors the schemas in `src/api/client.ts`. | P1 |

### 6.3 Data and contract gaps

| Gap | Current behaviour | Impact |
| --- | --- | --- |
| `quality="missing"` is never written | Omitted fields produce no row; there is no synthetic "missing" row | P3/P4 must treat absent rows as missing data, not expect `quality="missing"` |
| `contributing_factors` is unvalidated JSON | It is stored as `list[dict]` | P3 must keep the agreed `{indicator, observed, reference, note}` shape; bad values fail on JSON serialisation |
| `ActionHistory.updated_at` | Auto-updates on row changes via SQLAlchemy `onupdate` | P4 can rely on the timestamp for status changes |
| Cascade deletes | Crew-owned foreign keys declare `ON DELETE CASCADE`; `DELETE /crew/{id}` also deletes child rows explicitly in one transaction | No orphan rows after crew deletion |
| SQLite FK enforcement | `PRAGMA foreign_keys=ON` is enabled on every SQLite connection | SQLite tests match PostgreSQL FK behaviour |
| No migrations | Tables are created with `SQLModel.metadata.create_all()`; PostgreSQL enum members are reconciled additively | A destructive schema change still needs Alembic or a documented reset |
| No auth / rate limiting | All routes are open | Do not expose the service publicly without a gateway or auth |
| No idempotency key | The online-only frontend does not retry writes durably | Retrying clients can still create duplicate check-ins; add server-side idempotency before enabling retries |
| Readiness probe | `/health/ready` runs `SELECT 1` and returns `503` on database failure | Ops can detect a broken database |
| Request IDs | Every response carries `X-Request-ID` (client value or generated) | Easier tracing across frontend and backend |
| No CI / Dockerfile | Local commands only | Deployment is manual |

### 6.4 Test coverage gaps

Current tests cover the check-in transaction, hard/soft validation, history
filters, mission CRUD, `404` handling, the analysis hook, the unified overview
payload (mission clock, circadian invariance, status-rule provenance),
historical re-analysis (idempotency, history preservation, failure isolation,
`404`/`503`), crew create/delete cascades, assessment detail scoping, explicit
analysis runs, dashboard summaries, unified `422`s, `X-Total-Count`, repeated
history types, mission filters, and check-in source rejection.

Not yet covered as automated tests:

- Demo seed endpoint idempotency, `--reset`, `--analyze`, and `ENV=dev` gating.
- `load_engine()` dotted-path loading and startup failure on a bad path.
- CORS headers.
- P4 `Countermeasure` / `ActionHistory` persistence.
- Re-analysis against a real PostgreSQL database and large check-in sets.
- A browser end-to-end suite; the frontend build, lint, and a headless Chrome
  smoke test against the real API are run manually.

### 6.5 Before deployment

- Set `ENV=prod` so `/api/v1/demo/seed` returns `403`.
- Set `CORS_ORIGINS` to the deployed frontend origin.
- Set `DATABASE_URL` to the managed PostgreSQL instance and keep credentials in
  the host's secret manager; do not commit `backend/.env`.
- Add Alembic (or a documented reset procedure) before making destructive table
  changes. Additive PostgreSQL enum members are handled automatically.
- Add authentication/authorisation if the API is not kept behind a private gateway.
- Add CI to run `pytest`, frontend `npm run build`, and `npm run lint`.
