"""Tests for the rule-based conflict detector (``conflicts.py``).

Each rule has at least one positive and one negative case. The file also covers
midnight crossing, configurable thresholds, deterministic ids, unknown fatigue,
report ordering, and missing-data warnings.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.conflicts import (
    RULE_SET_VERSION,
    circadian_misalignment,
    detect_conflicts,
    high_fatigue_before_critical,
    insufficient_recovery,
    sleep_mission_conflict,
    workload_overload,
)
from app.mission.models import (
    AstronautContext,
    ConflictType,
    CrewProfileSummary,
    FatigueLevel,
    FatigueSignal,
    PlannedSleepWindow,
    Priority,
    Severity,
    SleepSummary,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
)
from app.models.enums import QualityFlag

UTC = timezone.utc
CREW_ID = "crew-1"

FORBIDDEN_WORDS = ("improve", "prevent", "medicat", "drug", "treatment")


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
    """Build a valid ``TaskView`` for conflict tests."""
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
    """Build a planned sleep window."""
    return PlannedSleepWindow(start_time=start, end_time=end, source=source)


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


def _critical_task(task_id: str = "critical", **kwargs: object) -> TaskView:
    """Build a critical, high-alertness task."""
    values: dict[str, object] = {
        "priority": Priority.critical,
        "workload": WorkloadLevel.high,
        "required_alertness": 5,
        "is_critical": True,
    }
    values.update(kwargs)
    return _task(task_id, **values)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rule 1: sleep_mission_conflict
# ---------------------------------------------------------------------------


def test_sleep_conflict_flags_overlap_with_planned_window() -> None:
    """A wake task overlapping a planned sleep window is a conflict."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task(start=_at(13, 21), end=_at(13, 23))

    outcome = sleep_mission_conflict(_context(planned=[window]), task)

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.rule_id == "R-SLEEP-WINDOW-01"
    assert conflict.conflict_type is ConflictType.sleep_window_conflict
    assert conflict.severity is Severity.high
    assert conflict.task_id == task.task_id
    assert conflict.affected_start == _at(13, 22)
    assert conflict.affected_end == _at(13, 23)
    assert "60 min" in conflict.explanation
    assert "R-SLEEP-WINDOW-01" in conflict.explanation
    assert "may reduce risk" in conflict.suggested_action
    assert conflict.config_keys == ["CONFLICT_OVERLAP_TOLERANCE_MINUTES"]


def test_sleep_conflict_ignores_a_task_outside_the_window() -> None:
    """A daytime task does not overlap a night sleep window."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task(start=_at(13, 9), end=_at(13, 10))

    assert sleep_mission_conflict(_context(planned=[window]), task).conflicts == []


def test_sleep_conflict_exempts_sleep_and_recovery_tasks() -> None:
    """A sleep/rest task may occupy the sleep window by design."""
    window = _window(_at(13, 22), _at(14, 6))
    for category in (
        TaskCategory.sleep,
        TaskCategory.rest,
        TaskCategory.rest_recovery,
    ):
        task = _task(
            start=_at(13, 22, 30),
            end=_at(13, 23, 30),
            category=category,
        )
        assert sleep_mission_conflict(_context(planned=[window]), task).conflicts == []


def test_sleep_conflict_handles_a_midnight_crossing_task() -> None:
    """The affected interval is the real intersection across midnight."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task(start=_at(13, 23, 30), end=_at(14, 0, 30))

    outcome = sleep_mission_conflict(_context(planned=[window]), task)

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.affected_start == _at(13, 23, 30)
    assert conflict.affected_end == _at(14, 0, 30)
    assert "60 min" in conflict.explanation


def test_sleep_conflict_honours_the_overlap_tolerance() -> None:
    """An overlap at or below the configured tolerance is suppressed."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task(start=_at(13, 21), end=_at(13, 23))
    config = MissionConfig(CONFLICT_OVERLAP_TOLERANCE_MINUTES=60)

    outcome = sleep_mission_conflict(_context(planned=[window]), task, config)

    assert outcome.conflicts == []


# ---------------------------------------------------------------------------
# Rule 2: insufficient_recovery
# ---------------------------------------------------------------------------


def test_recovery_conflict_flags_short_gap_between_demanding_tasks() -> None:
    """Ten free minutes between demanding tasks is below the 30 min default."""
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

    outcome = insufficient_recovery(context, current)

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.rule_id == "R-RECOVERY-01"
    assert conflict.conflict_type is ConflictType.insufficient_recovery_gap
    assert conflict.task_ids == ["demanding-1", "demanding-2"]
    assert conflict.affected_start == _at(13, 10)
    assert conflict.affected_end == _at(13, 10, 10)
    assert "10 free min" in conflict.explanation
    assert "30 min" in conflict.explanation


def test_recovery_conflict_ignores_a_sufficient_gap() -> None:
    """A one-hour gap is enough under the default 30 min threshold."""
    previous = _task(
        "demanding-1",
        start=_at(13, 8),
        end=_at(13, 10),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )
    current = _task(
        "demanding-2",
        start=_at(13, 11),
        end=_at(13, 13),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )

    outcome = insufficient_recovery(
        _context(tasks=[previous, current]), current
    )

    assert outcome.conflicts == []


def test_recovery_conflict_flags_demanding_task_after_short_sleep() -> None:
    """A short sleep followed by 10 free minutes triggers R-RECOVERY-02."""
    task = _task(
        "demanding",
        start=_at(13, 6, 10),
        end=_at(13, 8),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )

    outcome = insufficient_recovery(_context(sleep_minutes=330, tasks=[task]), task)

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.rule_id == "R-RECOVERY-02"
    assert conflict.task_ids == ["demanding"]
    assert "10 free min" in conflict.explanation
    assert "73% of the 450 min target" in conflict.explanation


def test_recovery_conflict_ignores_short_sleep_with_a_sufficient_gap() -> None:
    """The short-sleep rule needs both a short sleep and a short free gap."""
    task = _task(
        "demanding",
        start=_at(13, 7),
        end=_at(13, 9),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )

    outcome = insufficient_recovery(_context(sleep_minutes=330, tasks=[task]), task)

    assert outcome.conflicts == []


def test_recovery_conflict_ignores_non_demanding_tasks() -> None:
    """Recovery rules apply to demanding tasks only."""
    previous = _task(
        "demanding-1",
        start=_at(13, 8),
        end=_at(13, 10),
        workload=WorkloadLevel.high,
        required_alertness=5,
    )
    current = _task(
        "routine",
        start=_at(13, 10),
        end=_at(13, 11),
        workload=WorkloadLevel.low,
        required_alertness=2,
    )

    outcome = insufficient_recovery(
        _context(tasks=[previous, current]), current
    )

    assert outcome.conflicts == []


# ---------------------------------------------------------------------------
# Rule 3: high_fatigue_before_critical
# ---------------------------------------------------------------------------


def test_high_fatigue_before_critical_flags_monitor_level() -> None:
    """A monitor-level signal before a critical task is a high conflict."""
    outcome = high_fatigue_before_critical(
        _context(fatigue=FatigueLevel.monitor), _critical_task()
    )

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.rule_id == "R-FATIGUE-CRITICAL-01"
    assert conflict.conflict_type is ConflictType.high_fatigue_critical_task
    assert conflict.severity is Severity.high
    assert "monitor" in conflict.explanation
    assert "critical flag=True" in conflict.explanation
    assert outcome.warnings == []


def test_high_fatigue_before_critical_escalates_elevated_concern() -> None:
    """Elevated concern before a critical task is critical severity."""
    outcome = high_fatigue_before_critical(
        _context(fatigue=FatigueLevel.elevated_concern), _critical_task()
    )

    assert len(outcome.conflicts) == 1
    assert outcome.conflicts[0].severity is Severity.critical


def test_high_fatigue_before_critical_ignores_routine_task() -> None:
    """A monitor-level signal before a routine task is not this conflict."""
    task = _task(
        start=_at(13, 9),
        workload=WorkloadLevel.medium,
        required_alertness=3,
    )

    outcome = high_fatigue_before_critical(_context(fatigue=FatigueLevel.monitor), task)

    assert outcome.conflicts == []
    assert outcome.warnings == []


def test_unknown_fatigue_returns_a_warning_not_a_conflict() -> None:
    """Unknown fatigue must never be treated as a conflict or as no risk."""
    outcome = high_fatigue_before_critical(
        _context(fatigue=FatigueLevel.unknown), _critical_task()
    )

    assert outcome.conflicts == []
    assert len(outcome.warnings) == 1
    warning = outcome.warnings[0]
    assert warning.rule_id == "R-FATIGUE-DATA-01"
    assert warning.task_id == "critical"
    assert "unknown" in warning.message
    assert "No conflict was raised" in warning.message


# ---------------------------------------------------------------------------
# Rule 4: workload_overload
# ---------------------------------------------------------------------------


def _high_tasks(count: int, *, hours: int = 2) -> list[TaskView]:
    """Build consecutive high-workload tasks starting at 08:00."""
    tasks: list[TaskView] = []
    start = _at(13, 8)
    for index in range(count):
        end = start + timedelta(hours=hours)
        tasks.append(
            _task(
                f"high-{index + 1}",
                start=start,
                end=end,
                workload=WorkloadLevel.high,
                required_alertness=5,
            )
        )
        start = end
    return tasks


def test_workload_overload_flags_too_many_demanding_tasks() -> None:
    """Four demanding tasks in one 24 h window exceed the default maximum of 3."""
    tasks = _high_tasks(4)

    outcome = workload_overload(_context(tasks=tasks))

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.rule_id == "R-WORKLOAD-01"
    assert conflict.conflict_type is ConflictType.workload_overload
    assert conflict.severity is Severity.high
    assert conflict.task_ids == ["high-1", "high-2", "high-3", "high-4"]
    assert "4 demanding task(s)" in conflict.explanation
    assert "480 min" in conflict.explanation
    assert "MAX_DEMANDING_TASKS_PER_WINDOW" in conflict.config_keys


def test_workload_overload_ignores_a_balanced_schedule() -> None:
    """Three demanding tasks are at, not above, the default maximum."""
    outcome = workload_overload(_context(tasks=_high_tasks(3)))

    assert outcome.conflicts == []


def test_workload_overload_reads_the_configured_maximum() -> None:
    """Lowering the configured maximum makes three tasks an overload."""
    config = MissionConfig(MAX_DEMANDING_TASKS_PER_WINDOW=2)

    outcome = workload_overload(_context(tasks=_high_tasks(3)), config)

    assert len(outcome.conflicts) == 1
    assert "maximum is 2" in outcome.conflicts[0].explanation


def test_workload_overload_flags_excessive_demanding_minutes() -> None:
    """Cumulative demanding minutes above the cap escalate to critical."""
    config = MissionConfig(MAX_DEMANDING_TASK_HOURS_PER_WINDOW=300)
    tasks = _high_tasks(3, hours=3)

    outcome = workload_overload(_context(tasks=tasks), config)

    assert len(outcome.conflicts) == 1
    assert outcome.conflicts[0].severity is Severity.critical
    assert "540 min" in outcome.conflicts[0].explanation


# ---------------------------------------------------------------------------
# Rule 5: circadian_misalignment
# ---------------------------------------------------------------------------


def test_circadian_rule_flags_a_task_in_the_wocl() -> None:
    """A 03:00 task falls in the configured WOCL and sleep period."""
    task = _task(start=_at(13, 3), end=_at(13, 4))

    outcome = circadian_misalignment(_context(planned=[]), task)

    assert len(outcome.conflicts) == 1
    conflict = outcome.conflicts[0]
    assert conflict.rule_id == "R-CIRCADIAN-01"
    assert conflict.conflict_type is ConflictType.circadian_low_alertness
    assert conflict.severity is Severity.medium
    assert "WOCL" in conflict.explanation
    assert "03:00-04:00 UTC" in conflict.explanation
    assert "WOCL_START_HOUR" in conflict.config_keys


def test_circadian_rule_flags_habitual_sleep_period() -> None:
    """A task inside the inferred habitual sleep clock interval is flagged."""
    window = _window(_at(13, 22), _at(13, 23))
    task = _task(start=_at(13, 22, 15), end=_at(13, 22, 45))

    outcome = circadian_misalignment(_context(planned=[window]), task)

    assert len(outcome.conflicts) == 1
    assert "habitual sleep period" in outcome.conflicts[0].explanation
    assert "HABITUAL_SLEEP_MIN_RECORDS" in outcome.conflicts[0].config_keys


def test_circadian_rule_uses_the_configured_fallback_window() -> None:
    """Without an inferred window the protected clock window is used."""
    task = _task(start=_at(13, 23), end=_at(13, 23, 30))

    outcome = circadian_misalignment(_context(planned=[]), task)

    assert len(outcome.conflicts) == 1
    assert "protected sleep window" in outcome.conflicts[0].explanation
    assert "PROTECTED_SLEEP_WINDOW_START_HOUR" in outcome.conflicts[0].config_keys


def test_circadian_rule_ignores_a_midday_task() -> None:
    """A noon task is outside the sleep period and the WOCL."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task(start=_at(13, 12), end=_at(13, 13))

    assert circadian_misalignment(_context(planned=[window]), task).conflicts == []


def test_circadian_rule_exempts_sleep_tasks() -> None:
    """A sleep task at 03:00 is expected, not misaligned."""
    task = _task(
        start=_at(13, 3),
        end=_at(13, 4),
        category=TaskCategory.sleep,
    )

    assert circadian_misalignment(_context(planned=[]), task).conflicts == []


# ---------------------------------------------------------------------------
# Deterministic ids
# ---------------------------------------------------------------------------


def test_conflict_id_is_deterministic_for_the_same_inputs() -> None:
    """Re-evaluating the same task produces the same conflict id."""
    window = _window(_at(13, 22), _at(14, 6))
    task = _task(start=_at(13, 21), end=_at(13, 23))
    context = _context(planned=[window])

    first = sleep_mission_conflict(context, task).conflicts[0]
    second = sleep_mission_conflict(context, task).conflicts[0]

    assert first.conflict_id == second.conflict_id
    assert first.conflict_id.startswith("cf_")


def test_conflict_id_changes_with_task_or_rule() -> None:
    """A different task or rule produces a different id."""
    window = _window(_at(13, 22), _at(14, 6))
    context = _context(planned=[window])
    first_task = _task("task-1", start=_at(13, 21), end=_at(13, 23))
    second_task = _task("task-2", start=_at(13, 21), end=_at(13, 23))

    first = sleep_mission_conflict(context, first_task).conflicts[0]
    second = sleep_mission_conflict(context, second_task).conflicts[0]
    circadian = circadian_misalignment(context, first_task).conflicts[0]

    assert first.conflict_id != second.conflict_id
    assert first.conflict_id != circadian.conflict_id


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def test_detect_conflicts_returns_a_sorted_report() -> None:
    """The report aggregates rules and orders conflicts by affected start."""
    window = _window(_at(13, 22), _at(14, 6))
    critical = _task(
        "critical",
        start=_at(13, 23),
        end=_at(13, 23, 30),
        priority=Priority.critical,
        workload=WorkloadLevel.high,
        required_alertness=5,
        is_critical=True,
    )
    context = _context(
        fatigue=FatigueLevel.monitor,
        planned=[window],
        tasks=[critical],
    )

    report = detect_conflicts(context)

    assert report.astronaut_id == CREW_ID
    assert report.rule_set_version == RULE_SET_VERSION
    assert report.conflicts
    starts = [conflict.affected_start for conflict in report.conflicts]
    assert starts == sorted(starts)
    assert {conflict.rule_id for conflict in report.conflicts} >= {
        "R-SLEEP-WINDOW-01",
        "R-FATIGUE-CRITICAL-01",
    }
    assert all(conflict.conflict_id.startswith("cf_") for conflict in report.conflicts)
    assert all(conflict.task_id for conflict in report.conflicts)
    assert report.data_warnings == []
    assert "CONFLICT_OVERLAP_TOLERANCE_MINUTES" in report.config_keys


def test_detect_conflicts_skips_completed_and_cancelled_tasks() -> None:
    """Closed tasks are no longer evaluated."""
    window = _window(_at(13, 22), _at(14, 6))
    context = _context(
        planned=[window],
        tasks=[
            _task(
                "cancelled",
                start=_at(13, 22, 30),
                end=_at(13, 23),
                status=TaskStatus.cancelled,
            ),
            _task(
                "completed",
                start=_at(13, 22, 30),
                end=_at(13, 23),
                status=TaskStatus.completed,
            ),
        ],
    )

    report = detect_conflicts(context)

    assert report.conflicts == []
    assert report.data_warnings == []


def test_detect_conflicts_reports_missing_sleep_data() -> None:
    """Missing sleep history and sleep windows are explicit warnings."""
    context = _context(sleep_minutes=None, planned=[])

    report = detect_conflicts(context)

    assert report.conflicts == []
    rule_ids = {warning.rule_id for warning in report.data_warnings}
    assert rule_ids == {"R-DATA-SLEEP-WINDOW", "R-DATA-SLEEP-RECORD"}
    assert all(warning.astronaut_id == CREW_ID for warning in report.data_warnings)


def test_detect_conflicts_reports_unknown_fatigue_without_a_conflict() -> None:
    """Unknown fatigue yields a data warning and no critical-task conflict."""
    window = _window(_at(13, 22), _at(14, 6))
    context = _context(
        fatigue=FatigueLevel.unknown,
        planned=[window],
        tasks=[_critical_task(start=_at(13, 12), end=_at(13, 13))],
    )

    report = detect_conflicts(context)

    assert report.conflicts == []
    assert len(report.data_warnings) == 1
    assert report.data_warnings[0].rule_id == "R-FATIGUE-DATA-01"
    assert report.data_warnings[0].task_id == "critical"


def test_detect_conflicts_rejects_mixed_crew_tasks() -> None:
    """A context is single-crew; a foreign task is an error, not a guess."""
    context = _context(tasks=[_task(astronaut_id="crew-2")])

    with pytest.raises(ValueError):
        detect_conflicts(context)


def test_all_suggested_actions_are_review_oriented() -> None:
    """Suggested actions never claim improvement or mention medication."""
    window = _window(_at(13, 22), _at(14, 6))
    tasks = [
        _task(
            "critical",
            start=_at(13, 23),
            end=_at(13, 23, 30),
            priority=Priority.critical,
            workload=WorkloadLevel.high,
            required_alertness=5,
            is_critical=True,
        ),
        *_high_tasks(4),
    ]
    context = _context(
        fatigue=FatigueLevel.elevated_concern,
        sleep_minutes=330,
        planned=[window],
        tasks=tasks,
    )

    report = detect_conflicts(context)

    assert report.conflicts
    for conflict in report.conflicts:
        action = conflict.suggested_action.lower()
        assert "may reduce risk" in action
        assert "review" in action
        assert not any(word in action for word in FORBIDDEN_WORDS)


def test_detect_conflicts_is_deterministic() -> None:
    """The same context produces byte-identical reports."""
    window = _window(_at(13, 22), _at(14, 6))
    context = _context(
        fatigue=FatigueLevel.monitor,
        planned=[window],
        tasks=[
            _task(
                "critical",
                start=_at(13, 23),
                end=_at(13, 23, 30),
                priority=Priority.critical,
                workload=WorkloadLevel.high,
                required_alertness=5,
                is_critical=True,
            )
        ],
    )

    first = detect_conflicts(context)
    second = detect_conflicts(context, DEFAULT_CONFIG)

    assert first == second
