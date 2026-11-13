# Phase 5A — Advisory Recommendation Engine

Status: implementation and tests complete for Phase 5A. No database schema,
router, service, or file outside `backend/app/mission/` was changed, and
`mission_service.py` was not touched.

Files in this phase:

- `app/mission/recommendations.py` — the `generate_recommendations` entry point
  and one builder per conflict type.
- `app/mission/models.py` — `RecommendationType` and the expanded
  `Recommendation` contract.
- `app/mission/tests/test_recommendations.py` — per-type coverage,
  personalisation, deterministic ids, the medical-review flag, and the
  banned-word test.
- `app/mission/tests/test_models.py` — updated for the expanded required
  `Recommendation` fields.
- `app/mission/docs/05_recommendations.md` — this document.

Every recommendation is advisory decision support. Nothing is auto-applied, and
no recommendation claims that a schedule change improves fatigue. Final
authority remains with the crew, mission control, and medical staff
(`NASA-STD-3001-Vol2`, human-in-the-loop principle).

---

## 1. Entry point

```python
generate_recommendations(
    context: AstronautContext,
    conflicts: ConflictReport | Iterable[Conflict],
    config: MissionConfig = DEFAULT_CONFIG,
) -> list[Recommendation]
```

The function accepts either the `ConflictReport` produced by
`conflicts.detect_conflicts` or a plain iterable of `Conflict` objects. It
rejects a conflict that belongs to another astronaut with `ValueError`; a
context is single-crew by contract.

Output rules:

1. One recommendation per conflict, except `insufficient_data`, which produces
   none. A report containing only data warnings therefore returns `[]`.
2. Recommendations are ordered by priority (critical first), then related
   conflict id, then recommendation id.
3. At most `MAX_RECOMMENDATIONS_PER_RESPONSE` recommendations are returned.
4. The result is deterministic: the same context, conflicts, and config produce
   the same ids and text.

---

## 2. `Recommendation` contract

| Field | Type | Meaning |
| --- | --- | --- |
| `recommendation_id` | `str` | Deterministic hash, see Section 3. |
| `recommendation_type` | `RecommendationType` | One of the five Phase 5A action families. |
| `related_conflict_id` | `str` | The `conflict_id` that triggered the advice. |
| `astronaut_id` | `str` | Context owner. |
| `countermeasure_id` | `str` | `CM-01` ... `CM-07` from `docs/02_requirements.md`. |
| `countermeasure_name` | `str` | Full countermeasure name. |
| `rule_id` | `str` | Rule that detected the conflict. |
| `reason` | `str` | Inputs and measured values behind the finding, including personalisation. |
| `suggested_action` | `str` | Review-oriented action; names a suggested move against the task's current UTC schedule and contains "may reduce risk under rule X". |
| `expected_benefit` | `str` | Rule-level effect only; never a physiological claim. |
| `priority` | `Priority` | Derived from the conflict severity. |
| `explanation` | `str` | Scope and limitations of the recommendation. |
| `source_ids` | `list[str]` | Union of the conflict sources and the countermeasure sources. |
| `preconditions` | `list[str]` | What a human planner must confirm. |
| `warnings` | `list[str]` | Explicit limitations, including missing free gaps. |
| `requires_mission_approval` | `bool` | Always true; the module never applies a change. |
| `requires_medical_review` | `bool` | True only for the elevated-concern fatigue case, see Section 5. |
| `advisory_text` | `str` | Suggested action plus the human-authority statement. |

`RecommendationType` values:

- `review_task_timing`
- `identify_recovery_opportunity`
- `redistribute_demanding_tasks`
- `review_sleep_schedule`
- `evaluate_lighting_schedule`

---

## 3. Deterministic identifier

`recommendation_id` is `rc_` followed by the first 16 hexadecimal characters of
SHA-256 over this canonical payload:

```
astronaut_id | related_conflict_id | recommendation_type |
countermeasure_id | rule_id
```

The conflict id already covers the affected interval, task set, conflict type,
and rule. Re-evaluating the same inputs therefore produces the same id, while a
different conflict or action family produces a different one. Time is never
used as a random source.

---

## 4. Conflict-to-recommendation mapping

| Conflict type | Recommendation type | Countermeasure | Personalisation |
| --- | --- | --- | --- |
| `task_overlap` | `review_task_timing` | `CM-04` Redistribute High-Workload Tasks Across Schedule Windows | Involved task ids/names, overlap minutes, first free interval large enough for the longest task. |
| `sleep_window_conflict` | `review_sleep_schedule` | `CM-01` Protect / Reschedule Sleep Opportunity | The overlapping planned/inferred window, the crew sleep target, latest sleep duration and ratio to target. |
| `circadian_low_alertness` | `evaluate_lighting_schedule` | `CM-05` Adjust Lighting Exposure Schedule for Circadian Alignment | Task clock placement, habitual sleep reference, and the criterion that actually triggered the finding: the habitual sleep period, the configured fallback sleep window, the configured WOCL, or a combination. |
| `insufficient_recovery_gap` | `identify_recovery_opportunity` | `CM-03` Insert Structured Recovery / Rest Break Between Demanding Tasks | Free minutes in the conflict interval, required gap, first two usable free gaps, fatigue level, latest sleep ratio. |
| `workload_overload` | `redistribute_demanding_tasks` | `CM-04` Redistribute High-Workload Tasks Across Schedule Windows | Demanding task ids/names, count, cumulative minutes, configured caps. |
| `high_fatigue_critical_task` | `review_task_timing` | `CM-02` Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough | Categorical fatigue level and assessment source, critical task, required alertness. |
| `insufficient_data` | — | — | No recommendation is invented for missing data. |

The countermeasures are the only ones allowed by `docs/02_requirements.md`,
Section 3. A trigger with no mapped countermeasure returns no recommendation.

---

## 5. Personalisation

The generator uses only data from the supplied `AstronautContext`:

- `crew.sleep_target_hours` — rendered as hours and minutes and compared with
  the latest recorded sleep.
- `recent_sleep` — the latest interval's duration and percentage of the
  astronaut's own target.
- `planned_sleep_windows` — the source and clock interval of the inferred or
  planned habitual sleep window.
- `tasks` — task ids, names, durations, and the schedule used by
  `schedule.free_gaps`.
- `fatigue_signal` — the categorical level and assessment source. There is no
  numeric fatigue score.

Free-gap search:

1. Start at the conflict's `affected_start`.
2. Look forward for `PLANNING_HORIZON_HOURS`.
3. Use `MIN_STRUCTURED_BREAK_MINUTES` as the minimum recovery interval.
4. Exclude gaps that overlap a planned/inferred sleep window.
5. Report at most two candidates so the advisory text stays reviewable.

Two astronauts with different targets, windows, histories, tasks, or free gaps
therefore receive different text and may receive different actions (for
example, a concrete free interval versus a review-only warning when no gap
exists).

`requires_medical_review` is false by default. It is true only when the
recommendation depends on the highest categorical fatigue signal,
`elevated_concern`, from the health assessment. Monitor-level fatigue remains a
non-clinical schedule review.

---

## 6. Safety and scientific framing

1. Outputs are advisory indicators, not a diagnosis or a performance prediction.
   The module does not measure an individual's impairment.
2. No text recommends medication, a drug, a treatment, or a cure. The test
   suite rejects those words and the phrase "improve fatigue".
3. `expected_benefit` describes a rule-level effect, such as removing a measured
   overlap or meeting a configured recovery-gap rule. It never claims a
   physiological or performance gain.
4. Every action uses "consider", "review", and, where risk is mentioned, "may
   reduce risk under rule X".
5. `requires_mission_approval` is always true. `requires_medical_review` only
   flags the elevated-concern fatigue case for human medical review.
6. The module is deterministic and offline. It makes no network calls and
   persists nothing; `mission_service.py` is not wired yet.
7. All times are UTC. Crew-local time zones and individual circadian phase are
   not modelled.

---

## 7. Configuration keys used

| Key | Role |
| --- | --- |
| `PLANNING_HORIZON_HOURS` | Forward search window for free intervals. |
| `MIN_STRUCTURED_BREAK_MINUTES` | Minimum length of a suggested recovery break. |
| `MIN_RECOVERY_GAP_MINUTES` | Required free time named in recovery advice. |
| `MAX_DEMANDING_TASKS_PER_WINDOW` | Workload count cap named in redistribution advice. |
| `MAX_DEMANDING_TASK_HOURS_PER_WINDOW` | Workload minutes cap named in redistribution advice. |
| `WOCL_START_HOUR`, `WOCL_END_HOUR`, `WOCL_TOLERANCE_MINUTES` | Circadian clock window named in lighting advice only when the WOCL criterion triggered the finding. |
| `PROTECTED_SLEEP_WINDOW_START_HOUR`, `PROTECTED_SLEEP_WINDOW_END_HOUR` | Fallback sleep window when no inferred window exists. |
| `MAX_RECOMMENDATIONS_PER_RESPONSE` | Output cap. |

All values are configurable assumptions. The sources in `docs/01_references.md`
support the concepts but state no numeric threshold.

---

## 8. Test coverage

`app/mission/tests/test_recommendations.py` covers:

| Requirement | Tests |
| --- | --- |
| Each conflict type yields a recommendation | sleep, circadian, recovery, workload, high-fatigue, and task-overlap tests |
| `insufficient_data` behaviour | `test_insufficient_data_conflict_yields_no_recommendation`, `test_report_with_only_data_warnings_yields_no_recommendations` |
| Personalisation between two astronauts | `test_personalisation_differs_between_two_astronauts`, `test_recovery_personalisation_uses_each_astronauts_free_gaps` |
| Banned words | `test_banned_words_are_absent_from_all_recommendation_text` |
| Deterministic ids | `test_recommendation_ids_are_deterministic` |
| Medical-review flag | `test_high_fatigue_conflict_yields_timing_recommendation`, `test_elevated_concern_fatigue_flags_medical_review` |
| Real Phase 4 pipeline | `test_detect_conflicts_output_can_be_fed_to_generate_recommendations` |
| Cap and ordering | `test_recommendations_are_capped_and_priority_ordered` |
| Mixed-crew rejection | `test_recommendations_reject_a_conflict_for_another_astronaut` |

Run from `backend/`:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest app/mission/tests -q
```
