"""Tests for the what-if scenario module (``scenarios.py``).

The suite covers each of the five operations, input validation, immutability of
the original context, the rule-based comparison metrics, resolved/new conflict
listing, deterministic output, and the safety wording contract.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.mission.config import DEFAULT_CONFIG
from app.mission.models import (
    AstronautContext,
    ConflictType,
    CrewProfileSummary,
    FatigueLevel,
    FatigueSignal,
    PlannedSleepWindow,
    Priority,
    ScheduleMetrics,
    SleepSummary,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
)
from app.mission.scenarios import (
    FATIGUE_NOTE,
    add_recovery_period,
    compare,
    delay_task,
    modify_sleep_window,
    move_task,
    redistribute_workload,
)
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
    """Build a valid ``TaskView`` for scenario tests."""
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
    fatigue_source: str = "test-assessment",
    sleep_minutes: int | None = 465,
    planned: list[PlannedSleepWindow] | None = None,
    tasks: list[TaskView] | None = None,
) -> AstronautContext:
    """Build an astronaut context with an adequate recent sleep by default."""
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
        fatigue_signal=FatigueSignal(level=fatigue, source=fatigue_source),
        planned_sleep_windows=planned or [],
        tasks=tasks or [],
    )


def _high_task(
    task_id: str,
    *,
    start: datetime,
    end: datetime,
) -> TaskView:
    """Build a high-workload, high-alertness demanding task."""
    return _task(
        task_id,
        start=start,
        end=end,
        workload=WorkloadLevel.high,
        required_alertness=5,
    )


def _metric_count(metrics: ScheduleMetrics, conflict_type: ConflictType) -> int:
    """Return the comparison count for one conflict type."""
    for metric in metrics.conflicts_by_type:
        if metric.conflict_type is conflict_type:
            return metric.count
    return 0


# ---------------------------------------------------------------------------
# delay_task
# ---------------------------------------------------------------------------


def test_delay_task_shifts_the_task_and_preserves_duration() -> None:
    """Delaying moves both endpoints by the same amount."""
    task = _task(start=_at(13, 9), end=_at(13, 10, 30))
    context = _context(tasks=[task])

    proposed = delay_task(context, "task-1", 30)

    moved = proposed.tasks[0]
    assert moved.start_time == _at(13, 9, 30)
    assert moved.end_time == _at(13, 11)
    assert moved.duration_minutes == 90
    assert context.tasks[0].start_time == _at(13, 9)


def test_delay_task_rejects_unknown_and_closed_tasks() -> None:
    """A missing task or a closed task cannot be rescheduled."""
    closed = _task("closed", status=TaskStatus.completed)
    context = _context(tasks=[closed])

    with pytest.raises(ValueError):
        delay_task(context, "missing", 10)
    with pytest.raises(ValueError):
        delay_task(context, "closed", 10)


@pytest.mark.parametrize("minutes", [0, -15])
def test_delay_task_rejects_non_positive_minutes(minutes: int) -> None:
    """A delay must be a positive integer."""
    context = _context(tasks=[_task()])

    with pytest.raises(ValueError):
        delay_task(context, "task-1", minutes)


def test_delay_task_rejects_a_foreign_astronaut_task() -> None:
    """A context is single-crew by contract."""
    context = _context(tasks=[_task(astronaut_id="crew-2")])

    with pytest.raises(ValueError):
        delay_task(context, "task-1", 10)


# ---------------------------------------------------------------------------
# move_task
# ---------------------------------------------------------------------------


def test_move_task_moves_the_task_and_preserves_duration() -> None:
    """A move changes the start and keeps the duration."""
    task = _task(start=_at(13, 9), end=_at(13, 10, 30))
    context = _context(tasks=[task])

    proposed = move_task(context, "task-1", _at(13, 14))

    moved = proposed.tasks[0]
    assert moved.start_time == _at(13, 14)
    assert moved.end_time == _at(13, 15, 30)
    assert moved.duration_minutes == 90
    assert context.tasks[0].start_time == _at(13, 9)


def test_move_task_rejects_a_naive_start() -> None:
    """Naive datetimes are rejected instead of being guessed."""
    context = _context(tasks=[_task()])

    with pytest.raises(ValueError):
        move_task(context, "task-1", datetime(2026, 11, 13, 14, 0))


def test_move_task_rejects_an_unknown_task() -> None:
    """The task id must exist in the context."""
    context = _context(tasks=[_task()])

    with pytest.raises(ValueError):
        move_task(context, "missing", _at(13, 14))


# ---------------------------------------------------------------------------
# add_recovery_period
# ---------------------------------------------------------------------------


def test_add_recovery_period_inserts_and_shifts_following_tasks() -> None:
    """The default insert-and-shift creates a real recovery gap."""
    first = _high_task("demanding-1", start=_at(13, 8), end=_at(13, 10))
    second = _high_task("demanding-2", start=_at(13, 10, 10), end=_at(13, 12))
    context = _context(tasks=[first, second])

    proposed = add_recovery_period(context, _at(13, 10), _at(13, 10, 30))

    by_id = {task.task_id: task for task in proposed.tasks}
    assert len(proposed.tasks) == 3
    recovery = next(
        task
        for task in proposed.tasks
        if task.category is TaskCategory.rest_recovery
    )
    assert recovery.start_time == _at(13, 10)
    assert recovery.end_time == _at(13, 10, 30)
    assert recovery.task_id.startswith("rec_")
    assert by_id["demanding-1"].start_time == _at(13, 8)
    assert by_id["demanding-2"].start_time == _at(13, 10, 40)
    assert by_id["demanding-2"].end_time == _at(13, 12, 30)
    assert context.tasks[1].start_time == _at(13, 10, 10)


def test_add_recovery_period_is_deterministic() -> None:
    """Calling the operation twice on the same context yields the same id."""
    context = _context(tasks=[_high_task("d1", start=_at(13, 8), end=_at(13, 10))])

    first = add_recovery_period(context, _at(13, 10), _at(13, 10, 30))
    second = add_recovery_period(context, _at(13, 10), _at(13, 10, 30))

    first_ids = [task.task_id for task in first.tasks if task.task_id.startswith("rec_")]
    second_ids = [
        task.task_id for task in second.tasks if task.task_id.startswith("rec_")
    ]
    assert first_ids == second_ids


def test_add_recovery_period_without_shifting_keeps_tasks() -> None:
    """A pure insertion leaves the rest of the schedule untouched."""
    first = _high_task("demanding-1", start=_at(13, 8), end=_at(13, 10))
    second = _high_task("demanding-2", start=_at(13, 10, 10), end=_at(13, 12))
    context = _context(tasks=[first, second])

    proposed = add_recovery_period(
        context,
        _at(13, 10),
        _at(13, 10, 30),
        shift_following_tasks=False,
    )

    by_id = {task.task_id: task for task in proposed.tasks}
    assert by_id["demanding-2"].start_time == _at(13, 10, 10)


def test_add_recovery_period_rejects_an_invalid_interval() -> None:
    """Recovery periods need an ordered aware interval."""
    context = _context()

    with pytest.raises(ValueError):
        add_recovery_period(context, _at(13, 10), _at(13, 10))
    with pytest.raises(ValueError):
        add_recovery_period(
            context,
            datetime(2026, 11, 13, 10, 0),
            _at(13, 10, 30),
        )


def test_add_recovery_period_rejects_starting_inside_a_task() -> None:
    """Inserting in the middle of a task is ambiguous and rejected."""
    context = _context(tasks=[_task(start=_at(13, 9), end=_at(13, 10))])

    with pytest.raises(ValueError):
        add_recovery_period(context, _at(13, 9, 30), _at(13, 10))


def test_add_recovery_period_rejects_a_duplicate_task_id() -> None:
    """A caller-supplied id must not collide with an existing task."""
    context = _context(tasks=[_task("existing")])

    with pytest.raises(ValueError):
        add_recovery_period(
            context,
            _at(13, 11),
            _at(13, 11, 30),
            task_id="existing",
        )


# ---------------------------------------------------------------------------
# redistribute_workload
# ---------------------------------------------------------------------------


def test_redistribute_workload_moves_a_demanding_task() -> None:
    """A high-workload task can be moved to another slot."""
    task = _high_task("high-1", start=_at(13, 8), end=_at(13, 10))
    context = _context(tasks=[task])

    proposed = redistribute_workload(context, "high-1", _at(14, 8))

    moved = proposed.tasks[0]
    assert moved.start_time == _at(14, 8)
    assert moved.end_time == _at(14, 10)
    assert context.tasks[0].start_time == _at(13, 8)


def test_redistribute_workload_rejects_a_non_demanding_task() -> None:
    """Only demanding tasks may be redistributed."""
    context = _context(
        tasks=[
            _task(
                "routine",
                workload=WorkloadLevel.low,
                required_alertness=2,
            )
        ]
    )

    with pytest.raises(ValueError):
        redistribute_workload(context, "routine", _at(14, 8))


# ---------------------------------------------------------------------------
# modify_sleep_window
# ---------------------------------------------------------------------------


def test_modify_sleep_window_replaces_the_selected_window() -> None:
    """The selected window moves; the other window and source are preserved."""
    first = _window(_at(12, 22), _at(13, 6), source="first")
    second = _window(_at(13, 22), _at(14, 6), source="second")
    context = _context(planned=[first, second])

    proposed = modify_sleep_window(
        context,
        _at(13, 21, 30),
        _at(14, 5, 30),
        window_index=1,
    )

    assert proposed.planned_sleep_windows[0] == first
    changed = proposed.planned_sleep_windows[1]
    assert changed.start_time == _at(13, 21, 30)
    assert changed.end_time == _at(14, 5, 30)
    assert changed.source == "second"
    assert context.planned_sleep_windows[1].start_time == _at(13, 22)


def test_modify_sleep_window_rejects_missing_windows() -> None:
    """There must be a window to modify."""
    with pytest.raises(ValueError):
        modify_sleep_window(_context(), _at(13, 22), _at(14, 6))


@pytest.mark.parametrize("index", [-1, 1])
def test_modify_sleep_window_rejects_an_out_of_range_index(index: int) -> None:
    """The window index must address an existing window."""
    context = _context(planned=[_window(_at(13, 22), _at(14, 6))])

    with pytest.raises(ValueError):
        modify_sleep_window(context, _at(13, 21), _at(14, 5), window_index=index)


def test_modify_sleep_window_rejects_an_invalid_interval() -> None:
    """The replacement window must be an ordered aware interval."""
    context = _context(planned=[_window(_at(13, 22), _at(14, 6))])

    with pytest.raises(ValueError):
        modify_sleep_window(context, _at(14, 6), _at(13, 22))
    with pytest.raises(ValueError):
        modify_sleep_window(
            context,
            datetime(2026, 11, 13, 22, 0),
            _at(14, 6),
        )


# ---------------------------------------------------------------------------
# Original context immutability
# ---------------------------------------------------------------------------


def test_operations_do_not_mutate_the_original_context() -> None:
    """Every operation returns a copy and leaves the input intact."""
    first = _high_task("high-1", start=_at(13, 9), end=_at(13, 11))
    second = _high_task("high-2", start=_at(13, 11, 10), end=_at(13, 12))
    context = _context(
        planned=[_window(_at(13, 22), _at(14, 6))],
        tasks=[first, second],
    )
    snapshot = context.model_dump()

    delay_task(context, "high-1", 5)
    move_task(context, "high-1", _at(13, 13))
    add_recovery_period(context, _at(13, 13), _at(13, 13, 30))
    redistribute_workload(context, "high-2", _at(14, 8))
    modify_sleep_window(context, _at(13, 21), _at(14, 5))

    assert context.model_dump() == snapshot


# ---------------------------------------------------------------------------
# compare: validation
# ---------------------------------------------------------------------------


def test_compare_rejects_a_different_astronaut() -> None:
    """Both schedules must belong to the same astronaut."""
    original = _context(tasks=[_task()])
    proposed = _context(crew_id="crew-2", tasks=[_task()])

    with pytest.raises(ValueError):
        compare(original, proposed)


def test_compare_rejects_changed_fatigue_or_sleep_history() -> None:
    """Non-schedule inputs must be identical because fatigue is not re-predicted."""
    original = _context(tasks=[_task()])
    fatigue_changed = _context(fatigue=FatigueLevel.monitor, tasks=[_task()])
    sleep_changed = _context(sleep_minutes=360, tasks=[_task()])

    with pytest.raises(ValueError):
        compare(original, fatigue_changed)
    with pytest.raises(ValueError):
        compare(original, sleep_changed)


def test_compare_rejects_a_partial_window_override() -> None:
    """An explicit window needs both endpoints."""
    context = _context(tasks=[_task()])

    with pytest.raises(ValueError):
        compare(context, context, window_start=_at(13, 9))


def test_compare_rejects_a_naive_or_reversed_window() -> None:
    """Explicit windows use aware datetimes and a positive length."""
    context = _context(tasks=[_task()])

    with pytest.raises(ValueError):
        compare(
            context,
            context,
            window_start=datetime(2026, 11, 13, 9, 0),
            window_end=_at(13, 12),
        )
    with pytest.raises(ValueError):
        compare(
            context,
            context,
            window_start=_at(13, 12),
            window_end=_at(13, 9),
        )


def test_compare_rejects_an_empty_original_window() -> None:
    """Without a task or sleep boundary there is nothing to compare."""
    context = _context(tasks=[], planned=[])

    with pytest.raises(ValueError):
        compare(context, context)


# ---------------------------------------------------------------------------
# compare: metrics
# ---------------------------------------------------------------------------


def test_compare_reports_conflicts_by_type_and_copies_fatigue() -> None:
    """Conflicts are grouped by type and fatigue is the same input for both."""
    sleep_window = _window(_at(13, 22), _at(14, 6))
    night_task = _task(
        "night",
        start=_at(13, 22, 30),
        end=_at(13, 23, 30),
    )
    original = _context(planned=[sleep_window], tasks=[night_task])
    proposed = move_task(original, "night", _at(13, 12))

    comparison = compare(original, proposed)

    original_metrics = comparison.original_metrics
    proposed_metrics = comparison.proposed_metrics
    assert original_metrics.total_conflicts == 2
    assert _metric_count(
        original_metrics, ConflictType.sleep_window_conflict
    ) == 1
    assert _metric_count(
        original_metrics, ConflictType.circadian_low_alertness
    ) == 1
    assert proposed_metrics.total_conflicts == 0
    assert original_metrics.tasks_inside_sleep_windows == 1
    assert original_metrics.task_ids_inside_sleep_windows == ["night"]
    assert proposed_metrics.tasks_inside_sleep_windows == 0
    assert comparison.conflict_count_delta == -2
    assert comparison.resolved_conflicts
    assert comparison.new_conflicts == []
    assert {conflict.rule_id for conflict in comparison.resolved_conflicts} == {
        "R-SLEEP-WINDOW-01",
        "R-CIRCADIAN-01",
    }
    assert original_metrics.fatigue_level is FatigueLevel.no_flag
    assert original_metrics.fatigue_source == "test-assessment"
    assert proposed_metrics.fatigue_level is FatigueLevel.no_flag
    assert proposed_metrics.fatigue_source == "test-assessment"
    assert "fewer conflicts under the configured rules" in comparison.summary
    assert comparison.note == FATIGUE_NOTE


def test_compare_lists_new_conflicts() -> None:
    """Moving a task into a sleep window creates new conflicts."""
    sleep_window = _window(_at(13, 22), _at(14, 6))
    original = _context(
        planned=[sleep_window],
        tasks=[_task("day", start=_at(13, 9), end=_at(13, 10))],
    )
    proposed = move_task(original, "day", _at(13, 23))

    comparison = compare(original, proposed)

    assert comparison.original_metrics.total_conflicts == 0
    assert comparison.proposed_metrics.total_conflicts == 2
    assert comparison.conflict_count_delta == 2
    assert comparison.resolved_conflicts == []
    assert {conflict.rule_id for conflict in comparison.new_conflicts} == {
        "R-SLEEP-WINDOW-01",
        "R-CIRCADIAN-01",
    }
    assert "more conflicts under the configured rules" in comparison.summary


def test_compare_reports_workload_windows() -> None:
    """Workload windows mirror R-WORKLOAD-01 and report limits separately."""
    tasks = [
        _high_task("high-1", start=_at(13, 8), end=_at(13, 9)),
        _high_task("high-2", start=_at(13, 10), end=_at(13, 11)),
        _high_task("high-3", start=_at(13, 12), end=_at(13, 13)),
        _high_task("high-4", start=_at(13, 14), end=_at(13, 15)),
    ]
    original = _context(tasks=tasks)
    proposed = redistribute_workload(original, "high-4", _at(14, 20))

    comparison = compare(original, proposed)

    original_windows = comparison.original_metrics.workload_windows
    proposed_windows = comparison.proposed_metrics.workload_windows
    assert len(original_windows) == 1
    assert original_windows[0].demanding_task_count == 4
    assert original_windows[0].task_ids == [
        "high-1",
        "high-2",
        "high-3",
        "high-4",
    ]
    assert original_windows[0].exceeds_task_limit is True
    assert original_windows[0].exceeds_minutes_limit is False

    assert len(proposed_windows) == 2
    assert proposed_windows[0].demanding_task_count == 3
    assert proposed_windows[0].exceeds_task_limit is False
    assert proposed_windows[1].demanding_task_count == 1
    assert comparison.conflict_count_delta == -1
    assert [conflict.rule_id for conflict in comparison.resolved_conflicts] == [
        "R-WORKLOAD-01"
    ]


def test_add_recovery_reduces_the_recovery_conflict_count() -> None:
    """The constructed example loses its R-RECOVERY-01 conflict."""
    first = _high_task("demanding-1", start=_at(13, 8), end=_at(13, 10))
    second = _high_task("demanding-2", start=_at(13, 10, 10), end=_at(13, 12))
    original = _context(tasks=[first, second])
    proposed = add_recovery_period(original, _at(13, 10), _at(13, 10, 30))

    comparison = compare(original, proposed)

    assert (
        _metric_count(
            comparison.original_metrics,
            ConflictType.insufficient_recovery_gap,
        )
        == 1
    )
    assert (
        _metric_count(
            comparison.proposed_metrics,
            ConflictType.insufficient_recovery_gap,
        )
        == 0
    )
    assert comparison.original_metrics.total_conflicts == 1
    assert comparison.proposed_metrics.total_conflicts == 0
    assert comparison.conflict_count_delta == -1
    assert [conflict.rule_id for conflict in comparison.resolved_conflicts] == [
        "R-RECOVERY-01"
    ]
    assert comparison.new_conflicts == []
    assert comparison.proposed_metrics.total_recovery_minutes == 30
    assert comparison.original_metrics.total_recovery_minutes == 0
    assert comparison.proposed_metrics.longest_recovery_gap_minutes == 40
    assert comparison.original_metrics.longest_recovery_gap_minutes == 10
    assert "fewer conflicts under the configured rules" in comparison.summary


def test_compare_reports_free_time_and_accepts_a_window_override() -> None:
    """Free time uses the same explicit window for both schedules."""
    first = _high_task("demanding-1", start=_at(13, 8), end=_at(13, 10))
    second = _high_task("demanding-2", start=_at(13, 10, 10), end=_at(13, 12))
    original = _context(tasks=[first, second])
    proposed = add_recovery_period(original, _at(13, 10), _at(13, 10, 30))

    comparison = compare(
        original,
        proposed,
        window_start=_at(13, 8),
        window_end=_at(13, 12),
    )

    original_metrics = comparison.original_metrics
    proposed_metrics = comparison.proposed_metrics
    assert original_metrics.evaluation_start == _at(13, 8)
    assert original_metrics.evaluation_end == _at(13, 12)
    assert proposed_metrics.evaluation_start == _at(13, 8)
    assert proposed_metrics.evaluation_end == _at(13, 12)
    assert original_metrics.total_free_minutes == 10
    assert proposed_metrics.total_free_minutes == 10
    assert proposed_metrics.total_recovery_and_free_minutes == 40


def test_compare_is_deterministic_and_keeps_inputs_unchanged() -> None:
    """The same pair always produces the same comparison."""
    first = _high_task("demanding-1", start=_at(13, 8), end=_at(13, 10))
    second = _high_task("demanding-2", start=_at(13, 10, 10), end=_at(13, 12))
    original = _context(tasks=[first, second])
    proposed = add_recovery_period(original, _at(13, 10), _at(13, 10, 30))
    original_snapshot = original.model_dump()
    proposed_snapshot = proposed.model_dump()

    first_result = compare(original, proposed)
    second_result = compare(original, proposed, DEFAULT_CONFIG)

    assert first_result == second_result
    assert original.model_dump() == original_snapshot
    assert proposed.model_dump() == proposed_snapshot


def test_compare_config_keys_are_reported() -> None:
    """The comparison names the configuration keys its metrics depend on."""
    context = _context(tasks=[_high_task("d1", start=_at(13, 8), end=_at(13, 10))])

    comparison = compare(context, context)

    assert "MIN_RECOVERY_GAP_MINUTES" in comparison.config_keys
    assert "WORKLOAD_WINDOW_HOURS" in comparison.config_keys
    assert comparison.config_keys == sorted(set(comparison.config_keys))


# ---------------------------------------------------------------------------
# Safety wording
# ---------------------------------------------------------------------------


def test_banned_claims_are_absent_from_comparison_text() -> None:
    """The comparison never claims fatigue improvement or gives medical advice."""
    sleep_window = _window(_at(13, 22), _at(14, 6))
    original = _context(
        planned=[sleep_window],
        tasks=[
            _task("night", start=_at(13, 22, 30), end=_at(13, 23, 30)),
        ],
    )
    proposed = move_task(original, "night", _at(13, 12))

    comparison = compare(original, proposed)

    text = f"{comparison.summary} {comparison.note}".lower()
    assert comparison.note == FATIGUE_NOTE
    assert "fatigue was not re-predicted" in text
    assert "schedule rules only" in text
    assert not any(word in text for word in BANNED_WORDS)
    assert "improves" not in text
    assert "reduces fatigue" not in text
