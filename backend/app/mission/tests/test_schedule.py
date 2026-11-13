"""Tests for the pure schedule helpers (``schedule.py``)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.mission.models import (
    Priority,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
)
from app.mission.schedule import (
    daily_schedule,
    day_bounds,
    free_gaps,
    group_by_category,
    group_by_priority,
    priority_rank,
    recovery_periods,
    sleep_and_rest_periods,
    sleep_periods,
    sort_by_priority,
    week_bounds,
    weekly_schedule,
)

UTC = timezone.utc
DAY = date(2026, 11, 13)


def _task(
    task_id: str,
    start: datetime,
    end: datetime,
    *,
    astronaut_id: str = "crew-a",
    category: TaskCategory = TaskCategory.maintenance,
    priority: Priority = Priority.medium,
    workload: WorkloadLevel = WorkloadLevel.medium,
    required_alertness: int | None = 3,
    status: TaskStatus = TaskStatus.planned,
    is_critical: bool = False,
) -> TaskView:
    """Build a valid ``TaskView`` for schedule tests."""
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


def _at(hour: int, minute: int = 0, *, day: int = 13, month: int = 11) -> datetime:
    """Return an aware UTC datetime in November 2026."""
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Day and week windows
# ---------------------------------------------------------------------------


def test_day_bounds_normalises_datetime_to_utc() -> None:
    """An aware datetime is converted to UTC before its calendar day is taken."""
    offset = timezone(timedelta(hours=2))
    start, end = day_bounds(datetime(2026, 11, 14, 1, 0, tzinfo=offset))

    assert start == datetime(2026, 11, 13, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 14, 0, 0, tzinfo=UTC)


def test_day_bounds_rejects_naive_datetime() -> None:
    """A naive datetime is never guessed to be UTC."""
    with pytest.raises(ValueError):
        day_bounds(datetime(2026, 11, 13, 23, 0))


def test_week_bounds_covers_seven_days() -> None:
    """A week is seven consecutive UTC days."""
    start, end = week_bounds(date(2026, 11, 9))

    assert start == datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 16, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Daily and weekly grouping
# ---------------------------------------------------------------------------


def test_daily_schedule_groups_and_orders_multiple_astronauts() -> None:
    """Output is keyed per astronaut and sorted by start time."""
    tasks = [
        _task("b-late", _at(12), _at(13), astronaut_id="crew-b"),
        _task("a-late", _at(9), _at(10), astronaut_id="crew-a"),
        _task("a-early", _at(7), _at(8), astronaut_id="crew-a"),
    ]

    schedule = daily_schedule(tasks, DAY)

    assert list(schedule) == ["crew-a", "crew-b"]
    assert [task.task_id for task in schedule["crew-a"]] == ["a-early", "a-late"]
    assert [task.task_id for task in schedule["crew-b"]] == ["b-late"]


def test_daily_schedule_excludes_tasks_from_other_days() -> None:
    """Tasks outside the selected day are not included."""
    tasks = [
        _task("yesterday", _at(9, day=12), _at(10, day=12)),
        _task("today", _at(9, day=13), _at(10, day=13)),
        _task("tomorrow", _at(9, day=14), _at(10, day=14)),
    ]

    schedule = daily_schedule(tasks, DAY)

    assert [task.task_id for task in schedule["crew-a"]] == ["today"]


def test_daily_schedule_lists_midnight_crossing_task_on_both_days() -> None:
    """A task spanning midnight belongs to both calendar days."""
    crossing = _task(
        "crossing",
        _at(23, 30, day=13),
        _at(0, 30, day=14),
    )
    ends_at_midnight = _task(
        "ends-at-midnight",
        _at(23, 0, day=13),
        _at(0, 0, day=14),
    )

    day_thirteen = daily_schedule([crossing, ends_at_midnight], DAY)
    day_fourteen = daily_schedule([crossing, ends_at_midnight], date(2026, 11, 14))

    assert [task.task_id for task in day_thirteen["crew-a"]] == [
        "ends-at-midnight",
        "crossing",
    ]
    assert [task.task_id for task in day_fourteen["crew-a"]] == ["crossing"]


def test_daily_schedule_supports_different_sleep_patterns() -> None:
    """Each astronaut keeps their own sleep timing; no global assumption is made."""
    tasks = [
        _task(
            "a-sleep",
            _at(22, day=12),
            _at(6, day=13),
            astronaut_id="crew-a",
            category=TaskCategory.sleep,
        ),
        _task(
            "b-sleep",
            _at(1, day=13),
            _at(9, day=13),
            astronaut_id="crew-b",
            category=TaskCategory.sleep,
        ),
    ]

    schedule = daily_schedule(tasks, DAY)
    sleep, rest = sleep_and_rest_periods(tasks)

    assert [task.task_id for task in schedule["crew-a"]] == ["a-sleep"]
    assert [task.task_id for task in schedule["crew-b"]] == ["b-sleep"]
    assert [task.task_id for task in sleep] == ["a-sleep", "b-sleep"]
    assert rest == []
    assert schedule["crew-a"][0].start_time != schedule["crew-b"][0].start_time


def test_weekly_schedule_covers_the_seven_day_window() -> None:
    """The first and last days are included; the day after is not."""
    tasks = [
        _task("first-day", _at(8, day=9), _at(9, day=9)),
        _task("last-day", _at(23, day=15), _at(23, 30, day=15)),
        _task("after-week", _at(0, day=16), _at(1, day=16)),
    ]

    schedule = weekly_schedule(tasks, date(2026, 11, 9))

    assert [task.task_id for task in schedule["crew-a"]] == [
        "first-day",
        "last-day",
    ]


# ---------------------------------------------------------------------------
# Priority and category helpers
# ---------------------------------------------------------------------------


def test_priority_rank_orders_critical_above_low() -> None:
    """Ranks increase with urgency."""
    assert priority_rank(Priority.critical) == 4
    assert priority_rank(Priority.high) == 3
    assert priority_rank(Priority.medium) == 2
    assert priority_rank(Priority.low) == 1


def test_sort_by_priority_puts_urgent_tasks_first() -> None:
    """Sorting is by priority first, then by start time."""
    tasks = [
        _task("low", _at(7), _at(8), priority=Priority.low),
        _task("critical-late", _at(11), _at(12), priority=Priority.critical),
        _task("critical-early", _at(9), _at(10), priority=Priority.critical),
        _task("medium", _at(8), _at(9), priority=Priority.medium),
    ]

    ordered = sort_by_priority(tasks)

    assert [task.task_id for task in ordered] == [
        "critical-early",
        "critical-late",
        "medium",
        "low",
    ]


def test_group_helpers_cover_every_enum_member() -> None:
    """Both grouping helpers return a stable key set and sorted items."""
    tasks = [
        _task("sleep", _at(22), _at(23), category=TaskCategory.sleep),
        _task("rest", _at(12), _at(13), category=TaskCategory.rest),
        _task(
            "recovery",
            _at(14),
            _at(15),
            category=TaskCategory.rest_recovery,
            priority=Priority.high,
        ),
        _task("maintenance", _at(9), _at(10)),
    ]

    by_category = group_by_category(tasks)
    by_priority = group_by_priority(tasks)

    assert set(by_category) == set(TaskCategory)
    assert [task.task_id for task in by_category[TaskCategory.sleep]] == ["sleep"]
    assert [task.task_id for task in by_category[TaskCategory.rest]] == ["rest"]
    assert [task.task_id for task in by_category[TaskCategory.rest_recovery]] == [
        "recovery"
    ]
    assert set(by_priority) == set(Priority)
    assert [task.task_id for task in by_priority[Priority.high]] == ["recovery"]


def test_sleep_and_rest_periods_are_separated_and_ordered() -> None:
    """Sleep, rest, and rest_recovery are separated; other categories ignored."""
    tasks = [
        _task("sleep-late", _at(23), _at(23, 30), category=TaskCategory.sleep),
        _task("sleep-early", _at(1), _at(2), category=TaskCategory.sleep),
        _task("rest", _at(12), _at(13), category=TaskCategory.rest),
        _task("recovery", _at(14, 30), _at(15), category=TaskCategory.rest_recovery),
        _task("eva", _at(9), _at(10), category=TaskCategory.eva),
    ]

    sleep, recovery = sleep_and_rest_periods(tasks)

    assert [task.task_id for task in sleep] == ["sleep-early", "sleep-late"]
    assert [task.task_id for task in recovery] == ["rest", "recovery"]
    assert sleep_periods(tasks) == sleep
    assert recovery_periods(tasks) == recovery


# ---------------------------------------------------------------------------
# Free gaps
# ---------------------------------------------------------------------------


def test_free_gaps_merges_overlaps_and_applies_minimum() -> None:
    """Overlapping tasks merge; gaps shorter than the config minimum are omitted."""
    tasks = [
        _task("a", _at(9), _at(11)),
        _task("b", _at(10), _at(12)),
        _task("c", _at(12, 20), _at(13)),
        _task("d", _at(13, 10), _at(14)),
    ]

    gaps = free_gaps(tasks, _at(8), _at(18))

    assert [(gap.start_time, gap.end_time) for gap in gaps] == [
        (_at(8), _at(9)),
        (_at(12), _at(12, 20)),
        (_at(14), _at(18)),
    ]
    assert [gap.duration_minutes for gap in gaps] == [60, 20, 240]


def test_free_gaps_clips_tasks_to_the_window() -> None:
    """Tasks partially outside the window are clipped, not dropped."""
    tasks = [_task("early", _at(7), _at(10)), _task("late", _at(17), _at(20))]

    gaps = free_gaps(tasks, _at(8), _at(18))

    assert [(gap.start_time, gap.end_time) for gap in gaps] == [
        (_at(10), _at(17))
    ]


def test_free_gaps_returns_nothing_when_window_is_full() -> None:
    """A fully booked window has no gaps."""
    tasks = [_task("full", _at(8), _at(18))]

    assert free_gaps(tasks, _at(8), _at(18)) == []


def test_free_gaps_honours_explicit_minimum() -> None:
    """An explicit minimum overrides the configured threshold."""
    tasks = [_task("a", _at(9), _at(10)), _task("b", _at(10, 30), _at(11))]

    default_gaps = free_gaps(tasks, _at(8), _at(12))
    wide_gaps = free_gaps(tasks, _at(8), _at(12), min_minutes=60)

    assert [gap.duration_minutes for gap in default_gaps] == [60, 30, 60]
    assert [gap.duration_minutes for gap in wide_gaps] == [60, 60]


def test_free_gaps_rejects_naive_or_reversed_window() -> None:
    """Windows must be UTC-aware and positive."""
    with pytest.raises(ValueError):
        free_gaps([], datetime(2026, 11, 13, 8, 0), _at(18))
    with pytest.raises(ValueError):
        free_gaps([], _at(18), _at(8))
