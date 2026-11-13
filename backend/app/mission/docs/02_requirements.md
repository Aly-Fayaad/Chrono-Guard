# Phase 1 — Requirements: Mission Intelligence (Person 4)

Status: documentation only. No application code was written or changed in this phase.

## 0. Document control

- **Sole source of truth:** [`01_references.md`](./01_references.md). It defines three sources:
  `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2`.
- **Tag legend:**
  - `[Validated: <Source ID>]` — the statement is directly supported by that source in
    `01_references.md`.
  - `[Proposed logic]` — an engineering/design decision that is **not** stated in the sources.
- **Numeric rule:** no source in `01_references.md` states a numeric threshold. Every number used
  by this system is therefore a **configurable assumption** (Section 7), never a NASA finding.
- **Safety rule:** this module is decision support, not diagnosis. It must never recommend
  medication. Wording for every recommendation is "may reduce risk under rule X", not "improves"
  or "prevents".

---

## 1. Research Summary

- Spaceflight cognitive and operational performance decrements are driven by three interrelated
  factors: acute and chronic sleep loss (sleep restriction), circadian desynchronization, and work
  overload. `[Validated: NASA-HRP-Sleep-Risk]`
- Those decrements are linked to mission-critical scheduling demands, shifting sleep-wake
  schedules ("slam-shifts"), docking/undocking, extravehicular activities (EVAs), high-workload
  periods, and environmental factors such as noise, light, and microgravity.
  `[Validated: NASA-HRP-Sleep-Risk]`
- Sleep loss and circadian misalignment impair sustained attention (vigilance), working memory,
  cognitive throughput, reaction time, decision-making, and emotional regulation, increasing the
  risk of operational errors during critical tasks. `[Validated: NASA-HRP-Sleep-Risk]`
- Alertness and cognitive performance follow a circadian rhythm with predictable troughs during
  the biological night — the Window of Circadian Low (WOCL) — where error rates and sleepiness
  peak. `[Validated: NASA-TM-Fatigue-Countermeasures]`
- Consecutive days of restricted sleep produce cumulative performance degradation, and subjective
  self-assessment of fatigue often underestimates objective cognitive impairment.
  `[Validated: NASA-TM-Fatigue-Countermeasures]`
- Recovery from cumulative sleep restriction requires extended sleep opportunities rather than
  single short rest breaks; insufficient recovery intervals between demanding shifts sustain
  elevated fatigue risk. `[Validated: NASA-TM-Fatigue-Countermeasures]`
- Mission schedules must allocate sufficient daily time for sleep, personal hygiene, meals, and
  off-duty recovery to sustain crew health and performance across mission durations.
  `[Validated: NASA-STD-3001-Vol2]`
- Mission tasks vary in cognitive and physical demand; sustained excessive workload without
  adequate recovery degrades human-system performance and increases error probability.
  `[Validated: NASA-STD-3001-Vol2]`
- Spacecraft lighting systems must support both visual task performance and circadian entrainment
  through spectrum and illuminance control. `[Validated: NASA-STD-3001-Vol2]`
- Automated mission-planning and health-monitoring tools are intended to assist flight surgeons,
  mission planners, and crew; final operational and medical decisions remain with human
  authorities (Crew, Flight Surgeon / Medical Operations, and Mission Control).
  `[Validated: NASA-STD-3001-Vol2]`
- The system will turn these factors into explicit, configurable, explainable rules that flag
  schedule risk; it will not claim to measure an individual's actual impairment. `[Proposed logic]`
- The system will express every output as an advisory indicator with its rule, inputs, and source
  citation, so a human can accept, reject, or ignore it. `[Proposed logic]`

---

## 2. Factors Affecting Performance and Sleep/Workload Risks

### 2.1 Primary risk factors

- **Acute and chronic sleep loss / sleep restriction** degrade cognitive and operational
  performance. `[Validated: NASA-HRP-Sleep-Risk]`
- **Circadian desynchronization** — misalignment between endogenous circadian rhythms and the
  scheduled work/rest cycle — degrades performance. `[Validated: NASA-HRP-Sleep-Risk]`
- **Work overload** contributes to performance decrements. `[Validated: NASA-HRP-Sleep-Risk]`
- These three factors are interrelated and should be considered together rather than in
  isolation. `[Validated: NASA-HRP-Sleep-Risk]`

### 2.2 Operational and scheduling contributors

- Sleep curtailment and circadian misalignment occur with mission-critical scheduling demands,
  shifting sleep-wake schedules (slam-shifts), docking/undocking operations, EVAs, high-workload
  periods, and environmental factors (noise, light, microgravity).
  `[Validated: NASA-HRP-Sleep-Risk]`
- Schedules must reserve daily time for sleep, personal hygiene, meals, and off-duty recovery.
  `[Validated: NASA-STD-3001-Vol2]`
- Tasks differ in cognitive and physical demand; sustained excessive workload without recovery
  degrades performance and raises error probability. `[Validated: NASA-STD-3001-Vol2]`
- Lighting is a schedule-relevant factor because spacecraft lighting must support visual
  performance and circadian entrainment. `[Validated: NASA-STD-3001-Vol2]`

### 2.3 Performance impacts to flag

- Impaired sustained attention (vigilance), working memory, cognitive throughput, reaction time,
  decision-making, and emotional regulation; increased risk of operational errors in critical
  tasks. `[Validated: NASA-HRP-Sleep-Risk]`
- Predictable circadian troughs during the biological night (WOCL) where sleepiness and error
  rates peak. `[Validated: NASA-TM-Fatigue-Countermeasures]`
- Subjective fatigue self-assessment tends to underestimate objective impairment, so the absence
  of a self-reported complaint must not be treated as the absence of risk.
  `[Validated: NASA-TM-Fatigue-Countermeasures]`

### 2.4 Sleep debt and recovery

- Consecutive restricted-sleep days accumulate performance degradation.
  `[Validated: NASA-TM-Fatigue-Countermeasures]`
- Recovery requires extended sleep opportunities, not a single short rest break; short recovery
  intervals between demanding shifts sustain elevated fatigue risk.
  `[Validated: NASA-TM-Fatigue-Countermeasures]`
- Scheduled rest or nap periods are a mitigation strategy when consolidated nocturnal sleep is
  disrupted by mission operations. `[Validated: NASA-HRP-Sleep-Risk]`

### 2.5 System interpretation of these factors (proposed)

- Treat sleep restriction, circadian placement, and workload accumulation as three separate rule
  families that are combined only for explanation, never as a diagnosis. `[Proposed logic]`
- Represent the WOCL as a configurable clock-time window because the sources describe the
  phenomenon but give no clock times. `[Proposed logic]`
- Use the existing `SleepRecord` history as the only available sleep input; treat it as recorded
  actual sleep, not as a planned sleep opportunity. `[Proposed logic]`

---

## 3. Evidence-based Countermeasures

Only the seven countermeasures listed in `01_references.md` are allowed. No other
countermeasure may be added without first updating the source-of-truth file.

| ID | Countermeasure | Allowed sources | Notes |
| --- | --- | --- | --- |
| CM-01 | **Protect / Reschedule Sleep Opportunity** | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` | Operational/behavioral. Recommendation may say it "may reduce risk under rule X"; no efficacy magnitude is claimed. |
| CM-02 | **Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough** | `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures` | Applies to scheduling of high-criticality tasks; WOCL placement is checked by a configurable rule. |
| CM-03 | **Insert Structured Recovery / Rest Break Between Demanding Tasks** | `NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2` | Short breaks mitigate acute decline but do not replace extended recovery sleep. |
| CM-04 | **Redistribute High-Workload Tasks Across Schedule Windows** | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` | Spreads workload; does not claim a specific performance gain. |
| CM-05 | **Adjust Lighting Exposure Schedule for Circadian Alignment** | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` | Advisory only; the system cannot control spacecraft lighting. |
| CM-06 | **Strategic Short Nap / Rest Opportunity During Extended Operations** | `NASA-HRP-Sleep-Risk` | For extended operations where consolidated sleep is disrupted. |
| CM-07 | **Optimize Sleep Environment (Light/Noise Reduction)** | `NASA-HRP-Sleep-Risk` | Environmental guidance; no cabin-control capability is assumed. |

All seven are non-pharmacological, operational/behavioral countermeasures. **None of them is a
medical treatment, and the module must never generate medication advice.**

---

## 4. Functional Requirements

All functional behavior below is **[Proposed logic]** unless the "Source basis" column cites a
validated concept. The cited source supports the *concept*, not the specific rule or any numeric
threshold.

| ID | Requirement | Module | Source basis |
| --- | --- | --- | --- |
| FR-01 | Read crew context for evaluation: `CrewProfile` (including `sleep_target_hours`), recent `SleepRecord` and `HealthMeasurement` rows, the latest `Assessment`, and upcoming `MissionTask` rows — through `app/services/history_service.py` only; no direct writes. | `service.py` | Proposed logic (data-access contract from `00_repo_findings.md`) |
| FR-02 | Evaluate a candidate task window `(crew_id, start_time, end_time, task_type, workload_level, is_critical)` and detect: (a) overlap with other tasks of the same crew; (b) intrusion into the protected sleep opportunity; (c) placement inside the configured WOCL; (d) insufficient recovery gap around demanding tasks; (e) workload over-concentration in the affected day. | `conflicts.py` | Concepts: `NASA-HRP-Sleep-Risk` (sleep opportunity, workload), `NASA-TM-Fatigue-Countermeasures` (WOCL, recovery), `NASA-STD-3001-Vol2` (work-rest allocation). Rule logic: proposed logic. |
| FR-03 | Return a structured conflict report. Each finding carries `rule_id`, category, severity, affected interval, involved task ids, a human-readable explanation, the `source_ids` used, and the config values applied. | `conflicts.py`, `schemas.py` | Proposed logic |
| FR-04 | Compute non-diagnostic risk indicators from (i) sleep opportunity and sleep-debt proxy, (ii) circadian placement, (iii) workload distribution, and optionally (iv) the latest `Assessment.status`. Indicators are advisory only. | `risk.py` | Three drivers: `NASA-HRP-Sleep-Risk`; cumulative debt and WOCL: `NASA-TM-Fatigue-Countermeasures`; workload: `NASA-STD-3001-Vol2`. Scoring model: proposed logic. |
| FR-05 | Map triggered rules to countermeasures **only** from Section 3 (CM-01 … CM-07). A trigger with no mapped countermeasure returns no recommendation rather than inventing one. | `catalogue.py` | Per-countermeasure sources in Section 3 |
| FR-06 | Build each recommendation with the countermeasure id/name, the triggering rule, reason, `source_ids`, preconditions, warnings, `requires_mission_approval`, and wording of the form "may reduce risk under rule X". Never emit medication or treatment advice. | `catalogue.py`, `schemas.py` | Human-in-the-loop: `NASA-STD-3001-Vol2`; wording: project rule. Logic: proposed. |
| FR-07 | Expose read-only API endpoints: evaluate a proposed task window (what-if) and retrieve advisory recommendations for a crew member over a configured horizon. Endpoints must not create, update, or delete tasks. | `router.py` | Proposed logic |
| FR-08 | Accept transient "what-if" task windows that are never persisted; evaluation is computed per request. | `service.py`, `router.py` | Proposed logic |
| FR-09 | Provide a single callable conflict-check entry point that `mission_service.create_task` and `mission_service.update_task` can invoke, with `exclude_task_id` on update so a task does not conflict with itself. Wiring into `app/services/mission_service.py` is out of my folder and requires explicit approval. | `conflicts.py`; external `app/services/mission_service.py` | Proposed logic |
| FR-10 | Take every threshold, weight, horizon, and clock window from `config.py`; rule code contains no numeric literals for policy values. | `config.py` | Project rule; proposed logic |
| FR-11 | Include a rule-set version, the applied config identifiers, and the cited source ids in every response for traceability. | `schemas.py`, `service.py` | Proposed logic (supports NFR-02/NFR-08) |
| FR-12 | Degrade gracefully: if sleep history, tasks, or assessment data are missing/partial, or if `Assessment.contributing_factors` has an unexpected shape, return explicit "insufficient data" findings instead of inventing values. | `service.py`, `risk.py` | Proposed logic; informed by `00_repo_findings.md` (no defined `contributing_factors` schema; `insufficient_data` status exists). |
| FR-13 | Treat `Assessment` and the AI model as read-only inputs: never write assessments, never retrain/rebuild the model, never alter the database schema. | `service.py` | Project rule; human-in-the-loop principle from `NASA-STD-3001-Vol2`. Logic: proposed. |

---

## 5. Non-Functional Requirements

| ID | Requirement |
| --- | --- |
| NFR-01 | **Decision support only.** Outputs are advisory risk indications for crew, flight surgeons, mission planners, and mission control; the module must never make or execute operational or medical decisions. Final authority remains human (`NASA-STD-3001-Vol2`). |
| NFR-02 | **Explainability.** Every finding and recommendation must be traceable to a rule id, the inputs used, the threshold/weight applied, and at least one `source_id` where a source exists. No unexplained score may be emitted. |
| NFR-03 | **Configurable thresholds.** Every threshold, weight, and time window lives in `app/mission/config.py`, with a name, a docstring/comment, and a label of either "evidence-based (source: <ID/URL>)" or "configurable assumption". Rule modules must not hard-code policy numbers. |
| NFR-04 | **No medical advice.** No diagnosis, no medication, no treatment plan, no clinical claim. Only non-pharmacological operational/behavioral countermeasures from Section 3. |
| NFR-05 | **No required database changes.** Do not add or alter tables, columns, or models. Consume existing data through `history_service.py` and the `Assessment` table. Any optional persistence requires separate approval. |
| NFR-06 | **Testability.** Rules are pure/deterministic where possible and covered by pytest using the existing isolated in-memory SQLite fixtures (`tests/conftest.py`). Each rule family and each countermeasure mapping has at least one positive and one negative test. |
| NFR-07 | **Human-in-the-loop.** Recommendations are labelled advisory and never auto-applied; countermeasures that need mission approval are marked `requires_mission_approval`. |
| NFR-08 | **Traceability and versioning.** Responses expose a rule-set version and config snapshot identifier so a recommendation can be reproduced and audited later. |
| NFR-09 | **Robustness to missing/partial data.** No crashes on absent sleep history, absent assessments, undefined `contributing_factors` shapes, or sparse check-ins; degrade to explicit insufficient-data output. |
| NFR-10 | **Offline, deterministic, and dependency-light.** No network calls and no new runtime dependencies beyond the existing FastAPI/SQLModel/Pydantic v2 stack; identical inputs produce identical outputs; all time comparisons use UTC-aware datetimes. |
| NFR-11 | **Bounded work.** Queries and evaluations are limited to the configured planning horizon; no unbounded table scans or unbounded loops over historical data. |

---

## 6. Scientific Assumptions and Limitations

1. `01_references.md` contains **no numeric thresholds**. Every number introduced by this system
   is a configurable assumption and must be labelled as such; none may be presented as a NASA
   finding or a validated cut-off.
2. The sources describe risk relationships qualitatively. They do not provide a validated
   quantitative fatigue model, prediction equation, or individual-level risk score. Any scoring
   in this module is proposed system logic.
3. Only the seven countermeasures in Section 3 are allowed. Their effectiveness is **not**
   quantified in `01_references.md`; recommendations must use "may reduce risk under rule X"
   wording and must not claim improvement or prevention.
4. All countermeasures are non-pharmacological and operational/behavioral. The system is not a
   medical device, does not diagnose, and never recommends medication.
5. Subjective fatigue self-assessment can underestimate objective impairment
   (`NASA-TM-Fatigue-Countermeasures`); therefore the absence of a poor self-report is not
   evidence of safety, and the system must not treat it as such.
6. The existing `MissionTask` model has no task priority, no required alertness, and no task
   status; rules must not assume those fields exist (see `00_repo_findings.md`, gap list).
7. There are no planned sleep periods in the data model. `SleepRecord` is recorded actual sleep
   tied to a check-in, so "protected sleep opportunity" can only be approximated from a
   configurable clock window plus `CrewProfile.sleep_target_hours`.
8. `TaskType` has no `sleep` or `communication` value; a sleep-like block can only map to `rest`,
   and communication-like work falls under `other`. This limits task classification accuracy.
9. `Assessment` has no numeric fatigue score. It exposes categorical `status`, free-text
   `summary`/`explanation`, and an untyped `contributing_factors` list. No key names for that JSON
   are defined; the system must treat it defensively and must not rely on a fixed shape.
10. No database or model changes are allowed. Conflict results and recommendations are computed
    on demand and are not persisted unless a later change is explicitly approved.
11. The WOCL is individual and influenced by many factors; representing it as one fixed
    configurable clock window is a simplification.
12. Evidence comes from spaceflight human-research and aviation fatigue-management guidance;
    applicability to a specific crew, mission phase, or habitat requires human review.
13. The demo data are synthetic. No conclusion about real astronaut health can be drawn from this
    system's outputs.
14. The system does not monitor in real time and does not integrate with wearable or spacecraft
    systems; inputs are check-ins and scheduled tasks only.
15. All times are handled in UTC. Crew-local time and roster time zones are not modelled in the
    current data, which may shift the apparent WOCL and sleep window.
16. The system flags rule-based risk; it does not prove causation, predict an individual's
    performance, or replace the judgement of a flight surgeon.

---

## 7. Configurable Parameters

All parameters live in `app/mission/config.py` (to be created in a later phase). **No numeric
defaults are chosen in this phase.** The names below are proposed identifiers.

Every row's status is **configurable assumption**, because `01_references.md` states no numeric
value. The "Source anchor" column records the source that motivates the parameter's existence;
it does **not** validate any numeric value.

| Name | Meaning | Status | Source anchor |
| --- | --- | --- | --- |
| `PROTECTED_SLEEP_WINDOW_START` | Clock time at which the daily protected sleep opportunity begins. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` |
| `PROTECTED_SLEEP_WINDOW_END` | Clock time at which the daily protected sleep opportunity ends. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` |
| `MIN_SLEEP_OPPORTUNITY_HOURS` | Minimum uninterrupted sleep opportunity that the schedule should preserve. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` |
| `WOCL_START_HOUR` | Start of the configurable Window of Circadian Low. | Configurable assumption | `NASA-TM-Fatigue-Countermeasures` |
| `WOCL_END_HOUR` | End of the configurable Window of Circadian Low. | Configurable assumption | `NASA-TM-Fatigue-Countermeasures` |
| `SLEEP_HISTORY_LOOKBACK_DAYS` | How many days of sleep history feed the sleep-debt proxy. | Configurable assumption | `NASA-TM-Fatigue-Countermeasures` (cumulative sleep debt concept) |
| `CUMULATIVE_SLEEP_DEBT_THRESHOLD_HOURS` | Sleep deficit above which the debt indicator is raised. | Configurable assumption | `NASA-TM-Fatigue-Countermeasures` (concept only) |
| `HIGH_WORKLOAD_TASK_HOURS_PER_DAY` | Task-hours per day above which workload is treated as high. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` |
| `RECOVERY_GAP_MIN_HOURS` | Minimum recovery gap required between demanding tasks. | Configurable assumption | `NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2` |
| `MIN_STRUCTURED_BREAK_MINUTES` | Minimum duration of a structured rest break inside prolonged high workload. | Configurable assumption | `NASA-TM-Fatigue-Countermeasures` |
| `NAP_MIN_MINUTES` | Lower bound for a recommended strategic nap. | Configurable assumption | `NASA-HRP-Sleep-Risk` |
| `NAP_MAX_MINUTES` | Upper bound for a recommended strategic nap. | Configurable assumption | `NASA-HRP-Sleep-Risk` |
| `CRITICAL_TASK_ALERTNESS_REQUIREMENT` | Required alertness level for high-criticality tasks; used to compare task timing against alertness windows. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures` |
| `RISK_WEIGHT_SLEEP` | Weight of the sleep-related indicator in any combined risk indicator. | Configurable assumption | `NASA-HRP-Sleep-Risk` (factor only) |
| `RISK_WEIGHT_CIRCADIAN` | Weight of the circadian-placement indicator. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures` (factors only) |
| `RISK_WEIGHT_WORKLOAD` | Weight of the workload indicator. | Configurable assumption | `NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2` (factors only) |
| `RISK_FLAG_THRESHOLD` | Combined-indicator value at which an advisory flag is raised. | Configurable assumption | No source states a threshold |
| `CONFLICT_OVERLAP_TOLERANCE_MINUTES` | Allowed overlap/touching tolerance when detecting task conflicts. | Configurable assumption | No source states a tolerance |
| `PLANNING_HORIZON_HOURS` | Look-ahead window used by conflict checks and recommendations. | Configurable assumption | No source states a horizon |
| `INSUFFICIENT_DATA_MIN_DAYS` | Minimum history coverage before risk indicators are reported instead of "insufficient data". | Configurable assumption | No source states a minimum |
| `MAX_RECOMMENDATIONS_PER_RESPONSE` | Cap on recommendations returned per evaluation, to keep output reviewable. | Configurable assumption | No source states a cap |

---

## 8. References

Copied unchanged from `01_references.md`:

1. **`NASA-HRP-Sleep-Risk`** — *Evidence Report: Risk of Performance Decrements and Adverse Health
   Outcomes Resulting from Sleep Loss, Circadian Desynchronization, and Work Overload.* NASA Human
   Research Program (HRP) — Behavioral Health and Performance (BHP).
   <https://humanresearchroadmap.nasa.gov/evidence/reports/Sleep.pdf>
2. **`NASA-TM-Fatigue-Countermeasures`** — *Fatigue Countermeasures in Aviation and Spaceflight
   Operations* (NASA Technical Memorandum / Ames Research Center Fatigue Countermeasures Group).
   NASA Ames Research Center.
   <https://ntrs.nasa.gov/citations/20030062186>
3. **`NASA-STD-3001-Vol2`** — *NASA Spaceflight Human-System Standard, Volume 2: Human Factors,
   Habitability, and Environmental Health.* National Aeronautics and Space Administration (NASA).
   <https://standards.nasa.gov/standard/NASA/NASA-STD-3001-VOL-2>
