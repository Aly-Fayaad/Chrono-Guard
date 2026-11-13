"""Pure schedule helpers for mission intelligence.

No database access happens here: every function takes ``TaskView`` objects and
returns new objects. All time windows are handled in UTC and every policy
threshold (minimum free gap) comes from ``MissionConfig``.

Two conventions matter:

* A day or week is the half-open UTC interval ``[start, end)``. A task that
  crosses midnight therefore appears on every calendar day it overlaps, which
  is what a planner needs to see.
* Sleep is not assumed to happen at the same clock time for everyone. A sleep
  period is simply a task whose category is ``sleep``; each astronaut can have
  a different pattern.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Sequence

from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.models import (
    FreeGap,
    Priority,
    TaskCategory,
    TaskView,
)

SLEEP_CATEGORIES: frozenset[TaskCategory] = frozenset({TaskCategory.sleep})
"""Task categories treated as sleep periods."""

RECOVERY_CATEGORIES: frozenset[TaskCategory] = frozenset(
    {TaskCategory.rest, TaskCategory.rest_recovery}
)
"""Task categories treated as rest or recovery periods."""

_PRIORITY_RANK: dict[Priority, int] = {
    Priority.critical: 4,
    Priority.high: 3,
    Priority.medium: 2,
    Priority.low: 1,
}

_DAY = timedelta(days=1)
_WEEK = timedelta(days=7)


def _as_utc(value: datetime, label: str) -> datetime:
    """Require an aware datetime and normalise it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware (UTC)")
    return value.astimezone(timezone.utc)


def day_bounds(day: date | datetime) -> tuple[datetime, datetime]:
    """Return the half-open UTC interval for ``day``.

    A ``datetime`` is normalised to UTC first; a plain ``date`` is interpreted
    as that calendar day in UTC.
    """
    if isinstance(day, datetime):
        calendar_day = _as_utc(day, "day").date()
    else:
        calendar_day = day
    start = datetime.combine(calendar_day, time.min, tzinfo=timezone.utc)
    return start, start + _DAY


def week_bounds(week_start: date | datetime) -> tuple[datetime, datetime]:
    """Return the seven-day half-open UTC interval starting at ``week_start``."""
    start, _ = day_bounds(week_start)
    return start, start + _WEEK


def _sort_key(task: TaskView) -> tuple[datetime, str]:
    """Order tasks by start time, then by id for deterministic output."""
    return task.start_time, task.task_id


def _overlaps(task: TaskView, start: datetime, end: datetime) -> bool:
    """Return True when ``task`` overlaps the half-open interval ``[start, end)``."""
    return task.start_time < end and task.end_time > start


def daily_schedule(
    tasks: Iterable[TaskView], day: date | datetime
) -> dict[str, list[TaskView]]:
    """Group one day's tasks per astronaut, ordered by start time.

    A task is included when it overlaps the day interval, so midnight-crossing
    tasks appear on both days. Astronauts without tasks are omitted.
    """
    start, end = day_bounds(day)
    return _group_tasks(tasks, start, end)


def weekly_schedule(
    tasks: Iterable[TaskView], week_start: date | datetime
) -> dict[str, list[TaskView]]:
    """Group a seven-day schedule per astronaut, ordered by start time.

    The window starts at UTC midnight of ``week_start`` and covers seven days.
    """
    start, end = week_bounds(week_start)
    return _group_tasks(tasks, start, end)


def _group_tasks(
    tasks: Iterable[TaskView], start: datetime, end: datetime
) -> dict[str, list[TaskView]]:
    """Group tasks overlapping ``[start, end)`` by astronaut id."""
    grouped: dict[str, list[TaskView]] = defaultdict(list)
    for task in tasks:
        if _overlaps(task, start, end):
            grouped[task.astronaut_id].append(task)
    return {
        astronaut_id: sorted(items, key=_sort_key)
        for astronaut_id, items in sorted(grouped.items())
    }


def priority_rank(priority: Priority) -> int:
    """Return the urgency rank of a priority (critical=4, low=1)."""
    return _PRIORITY_RANK[priority]


def sort_by_priority(tasks: Iterable[TaskView]) -> list[TaskView]:
    """Return tasks most urgent first, then earliest first."""
    return sorted(
        tasks,
        key=lambda task: (
            -priority_rank(task.priority),
            task.start_time,
            task.task_id,
        ),
    )


def group_by_category(tasks: Iterable[TaskView]) -> dict[TaskCategory, list[TaskView]]:
    """Group tasks by category, ordered by start time.

    Every category is present, possibly with an empty list, so callers can rely
    on a stable shape.
    """
    grouped: dict[TaskCategory, list[TaskView]] = {
        category: [] for category in TaskCategory
    }
    for task in tasks:
        grouped[task.category].append(task)
    for items in grouped.values():
        items.sort(key=_sort_key)
    return grouped


def group_by_priority(tasks: Iterable[TaskView]) -> dict[Priority, list[TaskView]]:
    """Group tasks by priority, ordered by start time within each group."""
    grouped: dict[Priority, list[TaskView]] = {priority: [] for priority in Priority}
    for task in tasks:
        grouped[task.priority].append(task)
    for items in grouped.values():
        items.sort(key=_sort_key)
    return grouped


def sleep_periods(tasks: Iterable[TaskView]) -> list[TaskView]:
    """Return sleep-category tasks ordered by start time."""
    return sorted(
        (task for task in tasks if task.category in SLEEP_CATEGORIES),
        key=_sort_key,
    )


def recovery_periods(tasks: Iterable[TaskView]) -> list[TaskView]:
    """Return rest/rest-recovery tasks ordered by start time."""
    return sorted(
        (task for task in tasks if task.category in RECOVERY_CATEGORIES),
        key=_sort_key,
    )


def sleep_and_rest_periods(
    tasks: Iterable[TaskView],
) -> tuple[list[TaskView], list[TaskView]]:
    """Return ``(sleep_periods, recovery_periods)`` for the given tasks."""
    task_list = list(tasks)
    return sleep_periods(task_list), recovery_periods(task_list)


def free_gaps(
    tasks: Sequence[TaskView],
    window_start: datetime,
    window_end: datetime,
    config: MissionConfig = DEFAULT_CONFIG,
    min_minutes: int | None = None,
) -> list[FreeGap]:
    """Return unused intervals between tasks inside ``[window_start, window_end)``.

    Overlapping or touching tasks are merged before gaps are computed, and
    intervals are clipped to the window. A gap shorter than ``min_minutes``
    (default ``config.MIN_FREE_GAP_MINUTES``) is omitted as implicit buffer.

    All ``tasks`` must belong to the same astronaut; passing mixed crews would
    merge unrelated schedules.
    """
    start = _as_utc(window_start, "window_start")
    end = _as_utc(window_end, "window_end")
    if end <= start:
        raise ValueError("window_end must be after window_start")

    minimum = config.MIN_FREE_GAP_MINUTES if min_minutes is None else min_minutes
    if minimum < 0:
        raise ValueError("min_minutes must not be negative")

    intervals: list[tuple[datetime, datetime]] = []
    for task in tasks:
        clipped_start = max(task.start_time, start)
        clipped_end = min(task.end_time, end)
        if clipped_end > clipped_start:
            intervals.append((clipped_start, clipped_end))
    intervals.sort()

    merged: list[tuple[datetime, datetime]] = []
    for interval_start, interval_end in intervals:
        if merged and interval_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], interval_end))
        else:
            merged.append((interval_start, interval_end))

    gaps: list[FreeGap] = []
    cursor = start
    for interval_start, interval_end in merged:
        if interval_start > cursor:
            _append_gap(gaps, cursor, interval_start, minimum)
        cursor = max(cursor, interval_end)
    if end > cursor:
        _append_gap(gaps, cursor, end, minimum)
    return gaps


def _append_gap(
    gaps: list[FreeGap],
    start: datetime,
    end: datetime,
    minimum: int,
) -> None:
    """Append a gap when its whole-minute duration meets ``minimum``."""
    duration_minutes = int((end - start).total_seconds() // 60)
    if duration_minutes >= minimum:
        gaps.append(FreeGap(start_time=start, end_time=end))
