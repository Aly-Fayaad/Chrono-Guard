"""Tests for the task-suitability rules (``integration.py``).

Each test states the inputs, the expected status, and the rule ids that must
explain it. The "missing data" tests assert that no judgement is invented.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.mission.integration import evaluate_suitability, evaluate_upcoming
from app.mission.models import (
    AstronautContext,
    CrewProfileSummary,
    FatigueLevel,
    FatigueSignal,
    PlannedSleepWindow,
    Priority,
    SleepSummary,
    SuitabilityStatus,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
)
from app.models.enums import QualityFlag

UTC = timezone.utc
CREW_ID = "crew-1"


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
    """Build a valid ``TaskView`` for suitability tests."""
    start = start or datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    end = end or start + timedelta(hours=1)
    return TaskView(
        task_id=task_id,
        astronaut_id=astronaut_id,
        name=task_id,
        category=category,
        start_time=start,
        end_time=end,
        priority=priority,
        workload_level=workload,
        required_alertness=required_alertness,
        status=status,
        is_critical=is_critical,
    )


def _context(
    *,
    fatigue: FatigueLevel = FatigueLevel.no_flag,
    sleep_minutes: int | None = 465,
    target_hours: float = 7.5,
    planned: list[PlannedSleepWindow] | None = None,
    tasks: list[TaskView] | None = None,
) -> AstronautContext:
    """Build an astronaut context with one recent sleep record by default."""
    recent_sleep: list[SleepSummary] = []
    if sleep_minutes is not None:
        end = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)
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
            crew_id=CREW_ID,
            display_name="Crew One",
            role="commander",
            sleep_target_hours=target_hours,
        ),
        recent_sleep=recent_sleep,
        fatigue_signal=FatigueSignal(level=fatigue, source="test"),
        planned_sleep_windows=planned or [],
        tasks=tasks or [],
    )


# ---------------------------------------------------------------------------
# Suitable
# ---------------------------------------------------------------------------


def test_well_rested_astronaut_with_moderate_task_is_suitable() -> None:
    """No rule triggers for a rested astronaut on a non-demanding task."""
    context = _context(sleep_minutes=465)

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.suitable
    assert result.rule_ids == ["R-OK-01"]
    assert result.reasons == [
        "R-OK-01: no configured suitability rule was triggered."
    ]
    assert result.inputs_used["sleep_ratio"] == 1.033
    assert result.inputs_used["demanding"] is False
    assert result.inputs_used["overlaps_planned_sleep"] is False
    assert result.inputs_used["thresholds"]["SLEEP_SHORTFALL_REVIEW_RATIO"] == 0.9


def test_sleep_at_the_review_ratio_is_treated_as_adequate() -> None:
    """A shortfall smaller than the review ratio does not trigger R-SLEEP-02."""
    context = _context(sleep_minutes=420)  # 420/450 = 0.933

    result = evaluate_suitability(
        context,
        _task(workload=WorkloadLevel.high, required_alertness=5),
    )

    assert result.status is SuitabilityStatus.suitable
    assert "R-SLEEP-02" not in result.rule_ids


def test_non_demanding_task_ignores_a_moderate_sleep_shortfall() -> None:
    """R-SLEEP-02 applies to demanding tasks only."""
    context = _context(sleep_minutes=400)  # 400/450 = 0.889

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.suitable
    assert "R-SLEEP-02" not in result.rule_ids


@pytest.mark.parametrize(
    "category",
    [TaskCategory.sleep, TaskCategory.rest, TaskCategory.rest_recovery],
)
def test_sleep_and_recovery_tasks_may_occupy_a_sleep_window(
    category: TaskCategory,
) -> None:
    """The planned-sleep overlap rule exempts sleep/rest/recovery tasks."""
    window = PlannedSleepWindow(
        start_time=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
        end_time=datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
    )
    context = _context(planned=[window])
    task = _task(
        category=category,
        priority=Priority.low,
        workload=WorkloadLevel.low,
        required_alertness=2,
    )

    result = evaluate_suitability(context, task)

    assert result.status is SuitabilityStatus.suitable
    assert result.inputs_used["overlaps_planned_sleep"] is True
    assert result.inputs_used["protected_sleep_task"] is True


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


def test_monitor_fatigue_with_demanding_task_is_review() -> None:
    """R-FATIGUE-03 raises review for a demanding task under 'monitor'."""
    context = _context(fatigue=FatigueLevel.monitor)

    result = evaluate_suitability(
        context,
        _task(workload=WorkloadLevel.high, required_alertness=5),
    )

    assert result.status is SuitabilityStatus.review
    assert result.rule_ids == ["R-FATIGUE-03"]


def test_monitor_fatigue_with_non_demanding_task_is_low_review() -> None:
    """R-FATIGUE-04 still surfaces a review for a non-demanding task."""
    context = _context(fatigue=FatigueLevel.monitor)
    task = _task(
        priority=Priority.low,
        workload=WorkloadLevel.low,
        required_alertness=2,
    )

    result = evaluate_suitability(context, task)

    assert result.status is SuitabilityStatus.review
    assert result.rule_ids == ["R-FATIGUE-04"]


def test_moderate_sleep_shortfall_on_demanding_task_is_review() -> None:
    """R-SLEEP-02 fires when sleep is below the review ratio on a hard task."""
    context = _context(sleep_minutes=400)

    result = evaluate_suitability(
        context,
        _task(workload=WorkloadLevel.high, required_alertness=5),
    )

    assert result.status is SuitabilityStatus.review
    assert result.rule_ids == ["R-SLEEP-02"]
    assert result.inputs_used["sleep_ratio"] == 0.889
    assert "89% of the 450 min target" in result.reasons[0]


# ---------------------------------------------------------------------------
# Not recommended
# ---------------------------------------------------------------------------


def test_elevated_fatigue_with_critical_task_is_not_recommended() -> None:
    """A critical task under elevated concern is not recommended."""
    context = _context(fatigue=FatigueLevel.elevated_concern)
    task = _task(
        priority=Priority.critical,
        workload=WorkloadLevel.high,
        required_alertness=5,
        is_critical=True,
    )

    result = evaluate_suitability(context, task)

    assert result.status is SuitabilityStatus.not_recommended
    assert result.rule_ids == ["R-FATIGUE-01"]
    assert result.inputs_used["demanding"] is True


def test_severe_sleep_shortfall_on_demanding_task_is_not_recommended() -> None:
    """Below the severe ratio, a demanding task is not recommended."""
    context = _context(sleep_minutes=330)  # 330/450 = 0.733

    result = evaluate_suitability(
        context,
        _task(workload=WorkloadLevel.high, required_alertness=5),
    )

    assert result.status is SuitabilityStatus.not_recommended
    assert result.rule_ids == ["R-SLEEP-01"]
    assert result.inputs_used["sleep_ratio"] == 0.733


def test_severe_sleep_shortfall_on_non_demanding_task_is_review() -> None:
    """A severe shortfall is still only a review for a non-demanding task."""
    context = _context(sleep_minutes=330)

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.review
    assert result.rule_ids == ["R-SLEEP-01"]


def test_task_overlapping_planned_sleep_is_not_recommended() -> None:
    """R-SLEEP-03 protects an inferred/planned sleep window."""
    window = PlannedSleepWindow(
        start_time=datetime(2026, 11, 13, 8, 30, tzinfo=UTC),
        end_time=datetime(2026, 11, 13, 10, 30, tzinfo=UTC),
    )
    context = _context(planned=[window])

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.not_recommended
    assert result.rule_ids == ["R-SLEEP-03"]
    assert result.inputs_used["overlaps_planned_sleep"] is True


def test_multiple_findings_are_ordered_by_severity() -> None:
    """Reasons are ordered by severity, then rule id."""
    window = PlannedSleepWindow(
        start_time=datetime(2026, 11, 13, 8, 30, tzinfo=UTC),
        end_time=datetime(2026, 11, 13, 10, 30, tzinfo=UTC),
    )
    context = _context(
        fatigue=FatigueLevel.elevated_concern,
        sleep_minutes=330,
        planned=[window],
    )
    task = _task(
        priority=Priority.critical,
        workload=WorkloadLevel.high,
        required_alertness=5,
        is_critical=True,
    )

    result = evaluate_suitability(context, task)

    assert result.status is SuitabilityStatus.not_recommended
    assert result.rule_ids == ["R-FATIGUE-01", "R-SLEEP-01", "R-SLEEP-03"]


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------


def test_unknown_fatigue_returns_insufficient_data() -> None:
    """Unknown fatigue is missing data, never an implicit 'suitable'."""
    context = _context(fatigue=FatigueLevel.unknown)

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.insufficient_data
    assert result.rule_ids == ["R-DATA-01"]
    assert result.inputs_used["missing_inputs"] == ["fatigue_signal.level"]
    assert "fatigue_signal.level" in result.reasons[0]


def test_missing_sleep_returns_insufficient_data() -> None:
    """No sleep record means no sleep comparison is possible."""
    context = _context(sleep_minutes=None)

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.insufficient_data
    assert result.inputs_used["missing_inputs"] == ["recent_sleep"]
    assert result.inputs_used["last_sleep_minutes"] is None
    assert result.inputs_used["sleep_ratio"] is None


def test_zero_sleep_target_returns_insufficient_data() -> None:
    """An unusable crew sleep target is missing data, not a division by zero."""
    context = _context(target_hours=0.0)

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.insufficient_data
    assert result.inputs_used["missing_inputs"] == ["crew.sleep_target_hours"]


def test_all_missing_inputs_are_named_together() -> None:
    """Every missing input is reported, in a stable order."""
    context = _context(fatigue=FatigueLevel.unknown, sleep_minutes=None)

    result = evaluate_suitability(context, _task())

    assert result.status is SuitabilityStatus.insufficient_data
    assert result.inputs_used["missing_inputs"] == [
        "fatigue_signal.level",
        "recent_sleep",
    ]


def test_insufficient_data_status_is_exclusive() -> None:
    """'insufficient_data' never doubles as another status."""
    result = evaluate_suitability(
        _context(fatigue=FatigueLevel.unknown), _task()
    )

    assert result.status is SuitabilityStatus.insufficient_data
    assert result.status not in {
        SuitabilityStatus.suitable,
        SuitabilityStatus.review,
        SuitabilityStatus.not_recommended,
    }


# ---------------------------------------------------------------------------
# Upcoming evaluation
# ---------------------------------------------------------------------------


def test_evaluate_upcoming_orders_tasks_and_skips_closed_ones() -> None:
    """Only planned/in-progress tasks are evaluated, in start order."""
    tasks = [
        _task("late", start=datetime(2026, 11, 13, 15, 0, tzinfo=UTC)),
        _task(
            "completed",
            start=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
            status=TaskStatus.completed,
        ),
        _task("early", start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC)),
        _task(
            "cancelled",
            start=datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
            status=TaskStatus.cancelled,
        ),
        _task(
            "in-progress",
            start=datetime(2026, 11, 13, 11, 0, tzinfo=UTC),
            status=TaskStatus.in_progress,
        ),
    ]

    results = evaluate_upcoming(_context(tasks=tasks))

    assert [result.task_id for result in results] == [
        "early",
        "in-progress",
        "late",
    ]
    assert all(result.status is SuitabilityStatus.suitable for result in results)


def test_evaluate_upcoming_propagates_insufficient_data() -> None:
    """Missing data affects every task instead of defaulting to suitable."""
    tasks = [
        _task("one"),
        _task("two", start=datetime(2026, 11, 13, 11, 0, tzinfo=UTC)),
    ]

    results = evaluate_upcoming(
        _context(fatigue=FatigueLevel.unknown, tasks=tasks)
    )

    assert len(results) == 2
    assert all(
        result.status is SuitabilityStatus.insufficient_data for result in results
    )


def test_task_for_another_astronaut_is_rejected() -> None:
    """A context never evaluates another astronaut's task."""
    with pytest.raises(ValueError):
        evaluate_suitability(
            _context(),
            _task(astronaut_id="crew-2"),
        )


def test_evaluation_is_deterministic() -> None:
    """The same context and task produce the same result."""
    context = _context(fatigue=FatigueLevel.monitor)
    task = _task(workload=WorkloadLevel.high, required_alertness=5)

    first = evaluate_suitability(context, task)
    second = evaluate_suitability(context, task)

    assert first == second
