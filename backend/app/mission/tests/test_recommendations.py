"""Tests for the advisory recommendation generator (``recommendations.py``).

The tests cover every conflict type, deterministic ids, personalisation between
two astronauts, the review-only wording contract, medical-review flagging, and
the explicit no-recommendation behaviour for missing-data findings.
"""

from datetime import datetime, timedelta, timezone
from typing import Sequence

import pytest

from app.mission.config import MissionConfig
from app.mission.conflicts import circadian_misalignment, detect_conflicts
from app.mission.models import (
    AstronautContext,
    Conflict,
    ConflictReport,
    ConflictType,
    CrewProfileSummary,
    DataWarning,
    FatigueLevel,
    FatigueSignal,
    PlannedSleepWindow,
    Priority,
    RecommendationType,
    Severity,
    SleepSummary,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
)
from app.mission.recommendations import generate_recommendations
from app.models.enums import QualityFlag

UTC = timezone.utc
CREW_ID = "crew-1"
BANNED_WORDS = (
    "medication",
    "drug",
    "diagnose",
    "cure",
    "improve fatigue",
    "improve",
    "treatment",
    "prevent",
)

_RULE_BY_TYPE: dict[ConflictType, str] = {
    ConflictType.task_overlap: "R-TASK-OVERLAP-01",
    ConflictType.sleep_window_conflict: "R-SLEEP-WINDOW-01",
    ConflictType.circadian_low_alertness: "R-CIRCADIAN-01",
    ConflictType.insufficient_recovery_gap: "R-RECOVERY-01",
    ConflictType.workload_overload: "R-WORKLOAD-01",
    ConflictType.high_fatigue_critical_task: "R-FATIGUE-CRITICAL-01",
    ConflictType.insufficient_data: "R-FATIGUE-DATA-01",
}


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    """Return an aware UTC datetime in November 2026."""
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def _task(
    task_id: str = "task-1",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    astronaut_id: str = CREW_ID,
    category: TaskCategory = TaskCategory.maintenance,
    priority: Priority = Priority.medium,
    workload: WorkloadLevel = WorkloadLevel.medium,
    required_alertness: int | None = 3,
    status: TaskStatus = TaskStatus.planned,
    is_critical: bool = False,
) -> TaskView:
    """Build a valid ``TaskView`` for recommendation tests."""
    start = start or _at(13, 9)
    end = end or start + timedelta(hours=1)
    return TaskView(
        task_id=task_id,
        astronaut_id=astronaut_id,
        name=task_id.replace("-", " ").title(),
        category=category,
        start_time=start,
        end_time=end,
        priority=priority,
        workload_level=workload,
        required_alertness=required_alertness,
        status=status,
        is_critical=is_critical,
    )


def _window(
    start: datetime,
    end: datetime,
    source: str = "inferred_habitual_sleep",
) -> PlannedSleepWindow:
    """Build a planned or inferred sleep window."""
    return PlannedSleepWindow(start_time=start, end_time=end, source=source)


def _context(
    *,
    crew_id: str = CREW_ID,
    display_name: str = "Crew One",
    target_hours: float = 7.5,
    fatigue: FatigueLevel = FatigueLevel.no_flag,
    sleep_minutes: int | None = 465,
    planned: list[PlannedSleepWindow] | None = None,
    tasks: list[TaskView] | None = None,
) -> AstronautContext:
    """Build an astronaut context with one recent sleep record by default."""
    recent_sleep: list[SleepSummary] = []
    if sleep_minutes is not None:
        end = _at(13, 6)
        recent_sleep.append(
            SleepSummary(
                sleep_id="sleep-1",
                start_time=end - timedelta(minutes=sleep_minutes),
                end_time=end,
                interruptions=0,
                quality=QualityFlag.valid,
            )
        )
    return AstronautContext(
        crew=CrewProfileSummary(
            crew_id=crew_id,
            display_name=display_name,
            role="commander",
            sleep_target_hours=target_hours,
        ),
        recent_sleep=recent_sleep,
        fatigue_signal=FatigueSignal(level=fatigue, source="test-assessment"),
        planned_sleep_windows=planned or [],
        tasks=tasks or [],
    )


def _conflict(
    conflict_type: ConflictType,
    *,
    rule_id: str | None = None,
    severity: Severity = Severity.high,
    task_ids: Sequence[str] = ("task-1",),
    start: datetime | None = None,
    end: datetime | None = None,
    astronaut_id: str = CREW_ID,
    conflict_id: str | None = None,
    explanation: str = "Test conflict.",
) -> Conflict:
    """Build a valid ``Conflict`` for recommendation tests."""
    start = start or _at(13, 9)
    end = end or start + timedelta(hours=1)
    values: dict[str, object] = {
        "rule_id": rule_id or _RULE_BY_TYPE[conflict_type],
        "conflict_type": conflict_type,
        "severity": severity,
        "astronaut_id": astronaut_id,
        "task_ids": list(task_ids),
        "affected_start": start,
        "affected_end": end,
        "explanation": explanation,
        "suggested_action": "Review the finding.",
    }
    if conflict_id is not None:
        values["conflict_id"] = conflict_id
    return Conflict.model_validate(values)


def _critical_task(
    task_id: str = "critical",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> TaskView:
    """Build a critical, high-alertness task."""
    return _task(
        task_id,
        start=start or _at(13, 9),
        end=end or _at(13, 10),
        priority=Priority.critical,
        workload=WorkloadLevel.high,
        required_alertness=5,
        is_critical=True,
    )


def _rich_context() -> AstronautContext:
    """Build one context that can support every conflict type."""
    window = _window(_at(13, 22), _at(14, 6))
    tasks = [
        _task("overlap-a", start=_at(13, 8), end=_at(13, 9, 30)),
        _task("overlap-b", start=_at(13, 9), end=_at(13, 10)),
        _task(
            "demanding-1",
            start=_at(13, 10, 30),
            end=_at(13, 12),
            workload=WorkloadLevel.high,
            required_alertness=5,
        ),
        _task(
            "demanding-2",
            start=_at(13, 12, 10),
            end=_at(13, 14),
            workload=WorkloadLevel.high,
            required_alertness=5,
        ),
        _task(
            "high-1",
            start=_at(13, 15),
            end=_at(13, 17),
            workload=WorkloadLevel.high,
            required_alertness=5,
        ),
        _task(
            "high-2",
            start=_at(13, 17),
            end=_at(13, 19),
            workload=WorkloadLevel.high,
            required_alertness=5,
        ),
        _task(
            "high-3",
            start=_at(13, 19),
            end=_at(13, 21),
            workload=WorkloadLevel.high,
            required_alertness=5,
        ),
        _task(
            "high-4",
            start=_at(13, 21),
            end=_at(13, 22),
            workload=WorkloadLevel.high,
            required_alertness=5,
        ),
        _critical_task(start=_at(14, 3), end=_at(14, 4)),
    ]
    return _context(
        fatigue=FatigueLevel.elevated_concern,
        sleep_minutes=330,
        planned=[window],
        tasks=tasks,
    )


def _all_conflicts() -> list[Conflict]:
    """Build one conflict of each recommendation-producing type."""
    context = _rich_context()
    conflicts = [
        _conflict(
            ConflictType.task_overlap,
            conflict_id="cf_task_overlap",
            task_ids=["overlap-a", "overlap-b"],
            start=_at(13, 9),
            end=_at(13, 9, 30),
        ),
        _conflict(
            ConflictType.sleep_window_conflict,
            conflict_id="cf_sleep",
            task_ids=["high-4"],
            start=_at(13, 21),
            end=_at(13, 22),
        ),
        _conflict(
            ConflictType.circadian_low_alertness,
            conflict_id="cf_circadian",
            task_ids=["critical"],
            start=_at(14, 3),
            end=_at(14, 4),
            explanation=(
                "Rule R-CIRCADIAN-01: task 'critical' is inside the configured "
                "WOCL."
            ),
        ),
        _conflict(
            ConflictType.insufficient_recovery_gap,
            conflict_id="cf_recovery",
            task_ids=["demanding-1", "demanding-2"],
            start=_at(13, 12),
            end=_at(13, 12, 10),
        ),
        _conflict(
            ConflictType.workload_overload,
            conflict_id="cf_workload",
            task_ids=["high-1", "high-2", "high-3", "high-4"],
            start=_at(13, 15),
            end=_at(13, 22),
        ),
        _conflict(
            ConflictType.high_fatigue_critical_task,
            conflict_id="cf_fatigue",
            task_ids=["critical"],
            start=_at(14, 3),
            end=_at(14, 4),
            severity=Severity.critical,
        ),
    ]
    assert context.crew.crew_id == CREW_ID
    return conflicts


# ---------------------------------------------------------------------------
# One recommendation per conflict type
# ---------------------------------------------------------------------------


def test_sleep_window_conflict_yields_sleep_schedule_recommendation() -> None:
    """A sleep-window conflict yields CM-01 with the astronaut's own target."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task("night-work", start=_at(13, 21), end=_at(13, 23))
    context = _context(
        target_hours=7.5,
        sleep_minutes=330,
        planned=[window],
        tasks=[task],
    )
    conflict = _conflict(
        ConflictType.sleep_window_conflict,
        task_ids=["night-work"],
        start=_at(13, 22),
        end=_at(13, 23),
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type is RecommendationType.review_sleep_schedule
    assert recommendation.countermeasure_id == "CM-01"
    assert recommendation.rule_id == "R-SLEEP-WINDOW-01"
    assert recommendation.astronaut_id == CREW_ID
    assert recommendation.related_conflict_id == conflict.conflict_id
    assert recommendation.priority is Priority.high
    assert "7.5 h (450 min)" in recommendation.reason
    assert "330 min, 73% of the 450 min target" in recommendation.explanation
    assert "may reduce risk under rule R-SLEEP-WINDOW-01" in recommendation.suggested_action
    assert recommendation.requires_medical_review is False
    assert recommendation.requires_mission_approval is True


def test_moving_action_marks_the_interval_as_the_current_schedule() -> None:
    """A move suggestion must not present the task's interval as a proposal."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task("night-work", start=_at(13, 21), end=_at(13, 23))
    context = _context(planned=[window], tasks=[task])
    conflict = _conflict(
        ConflictType.sleep_window_conflict,
        task_ids=["night-work"],
        start=_at(13, 22),
        end=_at(13, 23),
    )

    recommendation = generate_recommendations(context, [conflict])[0]

    current_schedule = (
        "currently scheduled 2026-11-13 21:00 UTC to 2026-11-13 23:00 UTC"
    )
    assert current_schedule in recommendation.suggested_action
    assert current_schedule in recommendation.advisory_text
    assert " from 2026-11-13 21:00 UTC to " not in recommendation.suggested_action


def test_circadian_conflict_yields_lighting_recommendation() -> None:
    """Circadian misalignment yields CM-05 and names the lighting review."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task("night-science", start=_at(13, 3), end=_at(13, 4))
    context = _context(planned=[window], tasks=[task])
    conflict = _conflict(
        ConflictType.circadian_low_alertness,
        task_ids=["night-science"],
        start=_at(13, 3),
        end=_at(13, 4),
        severity=Severity.medium,
        explanation=(
            "Rule R-CIRCADIAN-01: task 'night-science' is inside the configured "
            "WOCL."
        ),
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type is RecommendationType.evaluate_lighting_schedule
    assert recommendation.countermeasure_id == "CM-05"
    assert recommendation.priority is Priority.medium
    assert "habitual sleep reference" in recommendation.reason
    assert "WOCL" in recommendation.reason
    assert "lighting exposure schedule" in recommendation.suggested_action
    assert "cannot control spacecraft lighting" in recommendation.expected_benefit


@pytest.mark.parametrize(
    ("task_start", "task_end", "window", "expected_term", "forbidden_term"),
    [
        (
            _at(13, 22, 15),
            _at(13, 22, 45),
            _window(_at(13, 22), _at(13, 23)),
            "habitual sleep period",
            "WOCL",
        ),
        (
            _at(13, 3),
            _at(13, 4),
            _window(_at(13, 10), _at(13, 18)),
            "configured WOCL",
            "habitual sleep period",
        ),
    ],
)
def test_lighting_recommendation_names_only_the_triggering_period(
    task_start: datetime,
    task_end: datetime,
    window: PlannedSleepWindow,
    expected_term: str,
    forbidden_term: str,
) -> None:
    """CM-05 refers to the WOCL only when the WOCL criterion triggered it."""
    task = _task("circadian-task", start=task_start, end=task_end)
    context = _context(planned=[window], tasks=[task])
    conflict = circadian_misalignment(context, task).conflicts[0]

    recommendation = generate_recommendations(context, [conflict])[0]

    assert recommendation.countermeasure_id == "CM-05"
    assert expected_term in recommendation.suggested_action
    assert expected_term in recommendation.advisory_text
    combined = " ".join(
        (
            recommendation.reason,
            recommendation.suggested_action,
            recommendation.expected_benefit,
            recommendation.explanation,
            recommendation.advisory_text,
        )
    )
    assert forbidden_term not in combined


def test_recovery_conflict_yields_recovery_recommendation_using_free_gaps() -> None:
    """An insufficient-recovery conflict yields CM-03 and a real free gap."""
    previous = _task(
        "demanding-1",
        start=_at(13, 8),
        end=_at(13, 10),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )
    current = _task(
        "demanding-2",
        start=_at(13, 10, 10),
        end=_at(13, 12),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )
    routine = _task(
        "routine",
        start=_at(13, 13),
        end=_at(13, 14),
        workload=WorkloadLevel.low,
        required_alertness=2,
    )
    context = _context(
        fatigue=FatigueLevel.monitor,
        tasks=[previous, current, routine],
    )
    conflict = _conflict(
        ConflictType.insufficient_recovery_gap,
        task_ids=["demanding-1", "demanding-2"],
        start=_at(13, 10),
        end=_at(13, 10, 10),
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type is RecommendationType.identify_recovery_opportunity
    assert recommendation.countermeasure_id == "CM-03"
    assert "10 free min" in recommendation.reason
    assert "configured minimum recovery gap is 30 min" in recommendation.reason
    assert "recorded fatigue level is 'monitor'" in recommendation.reason
    assert "2026-11-13 12:00 UTC" in recommendation.suggested_action
    assert "60 min available" in recommendation.suggested_action
    assert "at least 30 min" in recommendation.expected_benefit
    assert recommendation.requires_medical_review is False


def test_recovery_recommendation_reports_when_no_free_gap_exists() -> None:
    """A busy schedule produces a review-only recovery recommendation."""
    previous = _task(
        "demanding-1",
        start=_at(13, 8),
        end=_at(13, 10),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )
    current = _task(
        "demanding-2",
        start=_at(13, 10, 10),
        end=_at(13, 12),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )
    context = _context(tasks=[previous, current])
    conflict = _conflict(
        ConflictType.insufficient_recovery_gap,
        task_ids=["demanding-1", "demanding-2"],
        start=_at(13, 10),
        end=_at(13, 10, 10),
    )
    config = MissionConfig(PLANNING_HORIZON_HOURS=1)

    recommendations = generate_recommendations(context, [conflict], config)

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.warnings
    assert "No free interval was found" in recommendation.warnings[0]
    assert "schedule review" in recommendation.explanation


def test_workload_conflict_yields_redistribution_recommendation() -> None:
    """A workload conflict yields CM-04 with the task count and minutes."""
    tasks = [
        _task(
            f"high-{index}",
            start=_at(13, 8 + 2 * index),
            end=_at(13, 10 + 2 * index),
            workload=WorkloadLevel.high,
            required_alertness=5,
        )
        for index in range(4)
    ]
    context = _context(tasks=tasks)
    conflict = _conflict(
        ConflictType.workload_overload,
        task_ids=[task.task_id for task in tasks],
        start=_at(13, 8),
        end=_at(14, 8),
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type is RecommendationType.redistribute_demanding_tasks
    assert recommendation.countermeasure_id == "CM-04"
    assert "4 demanding task(s)" in recommendation.reason
    assert "480 demanding minutes" in recommendation.reason
    assert "high-1" in recommendation.suggested_action
    assert "at or below the configured 3 task(s)" in recommendation.expected_benefit


def test_high_fatigue_conflict_yields_timing_recommendation() -> None:
    """A monitor-level fatigue conflict stays non-clinical."""
    context = _context(
        fatigue=FatigueLevel.monitor,
        tasks=[_critical_task()],
    )
    conflict = _conflict(
        ConflictType.high_fatigue_critical_task,
        task_ids=["critical"],
        start=_at(13, 9),
        end=_at(13, 10),
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type is RecommendationType.review_task_timing
    assert recommendation.countermeasure_id == "CM-02"
    assert recommendation.priority is Priority.high
    assert "fatigue level 'monitor'" in recommendation.reason
    assert recommendation.requires_medical_review is False
    assert recommendation.warnings == []


def test_elevated_concern_fatigue_flags_medical_review() -> None:
    """Elevated concern is the only signal that flags medical review."""
    context = _context(
        fatigue=FatigueLevel.elevated_concern,
        tasks=[_critical_task()],
    )
    conflict = _conflict(
        ConflictType.high_fatigue_critical_task,
        task_ids=["critical"],
        start=_at(13, 9),
        end=_at(13, 10),
        severity=Severity.critical,
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.priority is Priority.critical
    assert recommendation.requires_medical_review is True
    assert "medical review is flagged" in recommendation.warnings[0]


def test_task_overlap_conflict_yields_timing_recommendation() -> None:
    """A plain task overlap yields CM-04 timing advice with a free interval."""
    first = _task("overlap-a", start=_at(13, 9), end=_at(13, 10, 30))
    second = _task("overlap-b", start=_at(13, 10), end=_at(13, 11))
    context = _context(tasks=[first, second])
    conflict = _conflict(
        ConflictType.task_overlap,
        rule_id="R-TASK-OVERLAP-01",
        task_ids=["overlap-a", "overlap-b"],
        start=_at(13, 10),
        end=_at(13, 10, 30),
        severity=Severity.medium,
    )

    recommendations = generate_recommendations(context, [conflict])

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type is RecommendationType.review_task_timing
    assert recommendation.countermeasure_id == "CM-04"
    assert recommendation.priority is Priority.medium
    assert "free interval starting 2026-11-13 11:00 UTC" in recommendation.suggested_action
    assert "may reduce risk under rule R-TASK-OVERLAP-01" in recommendation.suggested_action


def test_insufficient_data_conflict_yields_no_recommendation() -> None:
    """Missing-data findings are never turned into invented countermeasures."""
    context = _context(fatigue=FatigueLevel.unknown)
    conflict = _conflict(
        ConflictType.insufficient_data,
        rule_id="R-FATIGUE-DATA-01",
        start=_at(13, 9),
        end=_at(13, 10),
    )

    assert generate_recommendations(context, [conflict]) == []


def test_report_with_only_data_warnings_yields_no_recommendations() -> None:
    """Warnings alone do not produce an action."""
    context = _context(fatigue=FatigueLevel.unknown)
    report = ConflictReport(
        astronaut_id=CREW_ID,
        rule_set_version="test",
        conflicts=[],
        data_warnings=[
            DataWarning(
                rule_id="R-FATIGUE-DATA-01",
                astronaut_id=CREW_ID,
                task_id="critical",
                message="Fatigue level is unknown.",
            )
        ],
    )

    assert generate_recommendations(context, report) == []


# ---------------------------------------------------------------------------
# Integration with conflict detection
# ---------------------------------------------------------------------------


def test_detect_conflicts_output_can_be_fed_to_generate_recommendations() -> None:
    """The generator consumes a real ``ConflictReport`` from Phase 4."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task("night-work", start=_at(13, 21), end=_at(13, 23))
    context = _context(planned=[window], tasks=[task])

    report = detect_conflicts(context)
    recommendations = generate_recommendations(context, report)

    assert report.conflicts
    assert len(recommendations) == len(report.conflicts)
    assert {recommendation.related_conflict_id for recommendation in recommendations} == {
        conflict.conflict_id for conflict in report.conflicts
    }
    assert {
        recommendation.recommendation_type for recommendation in recommendations
    } == {
        RecommendationType.review_sleep_schedule,
        RecommendationType.evaluate_lighting_schedule,
    }
    assert all("may reduce risk under rule" in rec.advisory_text for rec in recommendations)


# ---------------------------------------------------------------------------
# Personalisation
# ---------------------------------------------------------------------------


def test_personalisation_differs_between_two_astronauts() -> None:
    """Sleep target, habitual window, and sleep history change the advice."""
    task_a = _task("night-work", start=_at(13, 21), end=_at(13, 23))
    context_a = _context(
        crew_id="crew-a",
        display_name="Crew A",
        target_hours=7.5,
        sleep_minutes=330,
        planned=[_window(_at(13, 22), _at(14, 6))],
        tasks=[task_a],
    )
    conflict_a = _conflict(
        ConflictType.sleep_window_conflict,
        task_ids=["night-work"],
        start=_at(13, 22),
        end=_at(13, 23),
        astronaut_id="crew-a",
        conflict_id="cf_shared",
    )

    task_b = _task("night-work", start=_at(13, 22), end=_at(14, 0))
    context_b = _context(
        crew_id="crew-b",
        display_name="Crew B",
        target_hours=8.5,
        sleep_minutes=480,
        planned=[_window(_at(13, 23), _at(14, 7))],
        tasks=[task_b],
    )
    conflict_b = _conflict(
        ConflictType.sleep_window_conflict,
        task_ids=["night-work"],
        start=_at(13, 23),
        end=_at(14, 0),
        astronaut_id="crew-b",
        conflict_id="cf_shared",
    )

    recommendation_a = generate_recommendations(context_a, [conflict_a])[0]
    recommendation_b = generate_recommendations(context_b, [conflict_b])[0]

    assert "7.5 h (450 min)" in recommendation_a.reason
    assert "8.5 h (510 min)" in recommendation_b.reason
    assert "73% of the 450 min target" in recommendation_a.explanation
    assert "94% of the 510 min target" in recommendation_b.explanation
    assert recommendation_a.reason != recommendation_b.reason
    assert recommendation_a.suggested_action != recommendation_b.suggested_action
    assert recommendation_a.recommendation_id != recommendation_b.recommendation_id


def test_recovery_personalisation_uses_each_astronauts_free_gaps() -> None:
    """One astronaut has a usable free gap; the other does not."""
    config = MissionConfig(PLANNING_HORIZON_HOURS=4)

    def _recovery_tasks(next_start: datetime, next_end: datetime) -> list[TaskView]:
        return [
            _task(
                "demanding-1",
                start=_at(13, 8),
                end=_at(13, 10),
                workload=WorkloadLevel.high,
                required_alertness=5,
            ),
            _task(
                "demanding-2",
                start=_at(13, 10, 10),
                end=_at(13, 12),
                workload=WorkloadLevel.high,
                required_alertness=5,
            ),
            _task("next-task", start=next_start, end=next_end),
        ]

    context_a = _context(
        crew_id="crew-a",
        tasks=_recovery_tasks(_at(13, 13), _at(13, 14)),
    )
    context_b = _context(
        crew_id="crew-b",
        tasks=_recovery_tasks(_at(13, 12), _at(13, 14)),
    )
    conflict_a = _conflict(
        ConflictType.insufficient_recovery_gap,
        task_ids=["demanding-1", "demanding-2"],
        start=_at(13, 10),
        end=_at(13, 10, 10),
        astronaut_id="crew-a",
        conflict_id="cf_shared",
    )
    conflict_b = _conflict(
        ConflictType.insufficient_recovery_gap,
        task_ids=["demanding-1", "demanding-2"],
        start=_at(13, 10),
        end=_at(13, 10, 10),
        astronaut_id="crew-b",
        conflict_id="cf_shared",
    )

    recommendation_a = generate_recommendations(context_a, [conflict_a], config)[0]
    recommendation_b = generate_recommendations(context_b, [conflict_b], config)[0]

    assert "60 min available" in recommendation_a.suggested_action
    assert recommendation_a.warnings == []
    assert "No free interval was found" in recommendation_b.warnings[0]
    assert recommendation_a.suggested_action != recommendation_b.suggested_action


# ---------------------------------------------------------------------------
# Determinism, ordering, and safety contract
# ---------------------------------------------------------------------------


def test_recommendation_ids_are_deterministic() -> None:
    """The same conflict produces the same recommendation id."""
    context = _rich_context()
    conflict = _all_conflicts()[1]

    first = generate_recommendations(context, [conflict])
    second = generate_recommendations(context, [conflict])
    other = generate_recommendations(
        context,
        [
            _conflict(
                ConflictType.sleep_window_conflict,
                task_ids=["high-4"],
                start=_at(13, 21),
                end=_at(13, 22),
                conflict_id="cf_other",
            )
        ],
    )

    assert [item.recommendation_id for item in first] == [
        item.recommendation_id for item in second
    ]
    assert first[0].recommendation_id.startswith("rc_")
    assert first[0].recommendation_id != other[0].recommendation_id


def test_recommendations_are_capped_and_priority_ordered() -> None:
    """The configured cap keeps the highest-priority recommendations."""
    context = _rich_context()
    conflicts = _all_conflicts()
    config = MissionConfig(MAX_RECOMMENDATIONS_PER_RESPONSE=2)

    recommendations = generate_recommendations(context, conflicts, config)

    assert len(recommendations) == 2
    assert [item.priority for item in recommendations] == [
        Priority.critical,
        Priority.high,
    ]
    assert {item.related_conflict_id for item in recommendations} == {
        "cf_circadian",
        "cf_fatigue",
    }


def test_recommendations_reject_a_conflict_for_another_astronaut() -> None:
    """A context is single-crew; a foreign conflict is an error, not a guess."""
    context = _context()
    conflict = _conflict(
        ConflictType.sleep_window_conflict,
        astronaut_id="crew-2",
    )

    with pytest.raises(ValueError):
        generate_recommendations(context, [conflict])


def test_conflict_report_and_conflict_list_are_equivalent() -> None:
    """A ``ConflictReport`` is accepted as a convenience input."""
    context = _rich_context()
    conflicts = _all_conflicts()
    report = ConflictReport(
        astronaut_id=CREW_ID,
        rule_set_version="test",
        conflicts=conflicts,
    )

    from_list = generate_recommendations(context, conflicts)
    from_report = generate_recommendations(context, report)

    assert [item.recommendation_id for item in from_list] == [
        item.recommendation_id for item in from_report
    ]


def test_banned_words_are_absent_from_all_recommendation_text() -> None:
    """No text claims medication, diagnosis, a cure, or an improvement."""
    context = _rich_context()
    config = MissionConfig(MAX_RECOMMENDATIONS_PER_RESPONSE=10)

    recommendations = generate_recommendations(context, _all_conflicts(), config)

    assert len(recommendations) == 6
    for recommendation in recommendations:
        texts = [
            recommendation.reason,
            recommendation.suggested_action,
            recommendation.expected_benefit,
            recommendation.explanation,
            recommendation.advisory_text,
            recommendation.countermeasure_name,
            *recommendation.preconditions,
            *recommendation.warnings,
        ]
        combined = " ".join(texts).lower()
        assert not any(word in combined for word in BANNED_WORDS), combined
        assert "may reduce risk under rule" in recommendation.advisory_text
        assert "decisions remain with the crew, mission control, and medical staff" in (
            recommendation.advisory_text.lower()
        )
        assert "no physiological effect is claimed" in (
            f"{recommendation.expected_benefit} {recommendation.explanation}".lower()
        )
