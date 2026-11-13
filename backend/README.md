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
│   │   ├── mission_clock.py     # backend-owned MET / D+ / local time
│   │   ├── reanalysis_service.py # additive, idempotent historical replay
│   │   └── analysis.py          # AnalysisEngine, NullEngine, load_engine
│   ├── ml/                      # CrewHealthEngine (vendored crew_health package)
│   ├── mission/__init__.py      # reserved for Person 4
│   └── seed/
│       ├── __init__.py
│       └── demo_data.py         # 3 scenarios + CLI
├── crew_health/                 # vendored three-process-model pipeline
├── tests/
│   ├── conftest.py
│   ├── test_checkins.py
│   ├── test_history.py
│   ├── test_missions.py
│   ├── test_overview.py
│   └── test_reanalysis.py
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
| GET | `/api/v1/crew/{crew_id}/overview` | Unified console payload: mission clock, series, detections, tasks, latest assessment |
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
| POST | `/api/v1/crew/{crew_id}/assessments/reanalyze` | Safe historical re-analysis of all stored check-ins (additive, idempotent) |
| POST | `/api/v1/demo/seed?scenario=...` | Seed one demo scenario (`ENV=dev` only) |

### Check-in contract

```json
{
  "recorded_at": "2026-11-13T22:00:00Z",
  "sleep": {"sleep_start": "...", "sleep_end": "...", "interruptions": 1},
  "behavioral": {"mood": 3, "sleepiness_kss": 6, "perceived_stress": 2},
  "cardiovascular": {"heart_rate": 72, "hrv": 60, "systolic_bp": 118, "diastolic_bp": 76},
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

# optional local configuration
copy .env.example .env              # PowerShell
# cp .env.example .env              # macOS / Linux
# Mission clock defaults: MISSION_EPOCH=2026-10-30T07:00:00Z, MISSION_DAY_HOURS=24.65
# (24.65 h is the operational Martian sol; circadian equations stay at 24 h.)
# Set ANALYSIS_ENGINE=app.services.analysis:NullEngine to disable analysis.

uvicorn app.main:app --reload
```

OpenAPI docs: <http://127.0.0.1:8000/docs>

```bash
# seed all three scenarios (skips existing demo crews)
python -m app.seed.demo_data

# seed one scenario and replace its data
python -m app.seed.demo_data --scenario reduced_recovery --reset

# alternative: HTTP seed endpoint while ENV=dev (also runs the analysis engine)
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
| Assessment deep-link route | Only list and latest exist | No `GET /crew/{id}/assessments/{assessment_id}` for a detail screen or deep link | P3 / backend |
| Guidance API | `Countermeasure` and `ActionHistory` tables exist, but there is no router, schema, or service | Frontend guidance panel has no endpoint; P4 must add and register a router | P4 |
| Countermeasure catalogue seed | No `Countermeasure` rows are seeded | `ActionHistory.countermeasure_id` cannot be populated; P4 must seed the catalogue | P4 |
| Action history API | `ActionHistory` is a table only | Accept / skip / complete actions and follow-up results are not exposed | P4 |
| Mission conflict / overlap logic | `mission_service` only checks `end_time > start_time` | `POST/PATCH /missions` returns no conflict warnings; P4 owns conflict detection | P4 |
| Mission approval workflow | `requires_mission_approval` is only a column | No approve/reject endpoint or status transition for P4 guidance | P4 |
| Crew onboarding | There is no `POST /crew`; only the seed creates crews | Frontend cannot create a crew; check-in and mission POSTs require an existing `crew_id` | Backend / P1 decision |
| Device import ingestion | `device_import` exists only in the source enum | No endpoint writes `source="device_import"`; `POST /checkins` always writes `manual` | Backend / P3 |

### 6.2 Frontend integration notes

| Behaviour | Why it matters | Owner |
| --- | --- | --- |
| `422` bodies have two shapes | Pydantic validation returns `detail: [...]`; domain validation returns `detail: "message"`. The frontend should handle both. | P1 / backend |
| `GET .../assessments/latest` returns `404` when empty | Treat `404` as "no assessment yet", not as a network failure. | P1 |
| `GET .../checkins` returns headers only | Measurements and sleep are in the detail route or history routes; the list is not a full record. | P1 |
| History responses are envelopes | Measurements arrive as `{"measurements": [...]}` and sleep as `{"sleep_records": [...]}`. | P1 |
| History `type` filter is single-valued | Multiple measurement types require multiple calls; the service helper accepts a list for P3/P4. | P1 |
| Health data aggregation | `GET /crew/{id}/overview` composes mission clock, series, detections, tasks, and assessment | Frontend no longer needs local aggregation for the console | done |
| No pagination totals | List routes return arrays without `total` or page counts. | P1 / backend |
| All timestamps are UTC | The UI must convert to the crew's local display time. | P1 |
| Units are fixed by the server | Display the returned `unit`; the client cannot submit units. | P1 |
| Mission list filters are limited | Only `upcoming`, `from`, and `to` are supported; no `task_type`, `workload_level`, or `is_critical` filters yet. | P4 / P1 |
| Upcoming semantics differ | The HTTP route returns all future tasks; `history_service.get_upcoming_tasks()` defaults to a 72-hour horizon. P3/P4 must agree which one they use. | P3 / P4 |
| No API client is generated | `/openapi.json` is available; the frontend can generate types or mirror the schemas manually. | P1 |

### 6.3 Data and contract gaps

| Gap | Current behaviour | Impact |
| --- | --- | --- |
| `quality="missing"` is never written | Omitted fields produce no row; there is no synthetic "missing" row | P3/P4 must treat absent rows as missing data, not expect `quality="missing"` |
| `contributing_factors` is unvalidated JSON | It is stored as `list[dict]` | P3 must keep the agreed `{indicator, observed, reference, note}` shape; bad values fail on JSON serialisation |
| `ActionHistory.updated_at` is not auto-updated | It only has a default | P4 must set it on every status change |
| No cascade deletes | Foreign keys have no `ondelete` behaviour; the seed deletes dependent rows manually | A future `DELETE /crew` must clean up all child tables |
| SQLite FK enforcement is off | FKs are declared, but SQLite does not enforce them unless the pragma is enabled | Orphan rows are possible outside the seed's manual cleanup |
| No migrations | Tables are created with `SQLModel.metadata.create_all()` | Any schema change by P3/P4 requires a DB reset or adding Alembic |
| No auth / rate limiting | All routes are open | Do not expose the service publicly without a gateway or auth |
| No sync / offline / idempotency | Out of scope by design | Duplicate check-in POSTs create duplicate records |
| No DB check in `/health` | It returns a static status | Ops cannot detect a broken database from the health route |
| No request IDs or logging config | Default Uvicorn logging only | Harder to trace errors across P1/P3/P4 |
| No CI / Dockerfile | Local commands only | Deployment is manual |

### 6.4 Test coverage gaps

Current tests cover the check-in transaction, hard/soft validation, history
filters, mission CRUD, `404` handling, the analysis hook, the unified overview
payload (mission clock, circadian invariance, status-rule provenance), and
historical re-analysis (idempotency, history preservation, failure isolation,
`404`/`503`). Not yet covered:

- Crew list/detail/PATCH routes and their `404` cases.
- Assessment list/latest empty-state behaviour beyond the overview path.
- Demo seed endpoint idempotency, `--reset`, and `ENV=dev` gating.
- `load_engine()` dotted-path loading and startup failure on a bad path.
- Sleep duration hard/soft bounds and interruption bounds as automated tests.
- Check-in and history pagination limits.
- CORS headers.
- P4 `Countermeasure` / `ActionHistory` persistence.
- Re-analysis against a real (non-in-memory) database and large check-in sets.

### 6.5 Before deployment

- Set `ENV=prod` so `/api/v1/demo/seed` returns `403`.
- Set `CORS_ORIGINS` to the deployed frontend origin.
- Add Alembic (or a documented reset procedure) before changing tables.
- Enable SQLite `PRAGMA foreign_keys=ON` or add explicit cascade cleanup.
- Add authentication/authorisation if the API is not kept behind a private gateway.
- Install the appropriate driver if `DATABASE_URL` is changed from SQLite.
- Add CI to run `pytest` and a lint/type check.
