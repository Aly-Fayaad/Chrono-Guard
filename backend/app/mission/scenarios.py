"""Pure what-if scenario analysis for mission intelligence.

Every operation in this module is in-memory and read-only with respect to the
database. An operation takes an ``AstronautContext`` and returns a new context;
the input context is never mutated. Nothing is persisted and no service or
router is imported.

The five operations are deliberately small schedule edits:

* :func:`delay_task` - shift one task later by a number of minutes.
* :func:`move_task` - move one task to a chosen start time.
* :func:`add_recovery_period` - add a recovery block. By default the block is
  inserted and later open tasks are pushed forward, because a recovery block
  that merely overlaps existing work cannot create a recovery opportunity under
  the Phase 4 rules.
* :func:`redistribute_workload` - move one named demanding task to another slot.
* :func:`modify_sleep_window` - replace one planned/inferred sleep window.

:func:`compare` evaluates the original and the proposed context with the Phase 4
conflict rules and reports rule-based metrics only. Fatigue is **not**
re-predicted: the comparison copies the original categorical fatigue signal into
both metric sets and states that limitation explicitly. The output never claims
that a schedule change improves fatigue or performance.

All times are UTC-aware and every threshold comes from ``MissionConfig``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.conflicts import detect_conflicts
from app.mission.models import (
    AstronautContext,
    Conflict,
    ConflictReport,
    ConflictType,
    ConflictTypeMetric,
    FatigueLevel,
    Priority,
    ScenarioComparison,
    ScheduleMetrics,
    Severity,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
    WorkloadWindowMetric,
)
from app.mission.schedule import RECOVERY_CATEGORIES, SLEEP_CATEGORIES, free_gaps

FATIGUE_NOTE = (
    "Fatigue was not re-predicted; this comparison reflects schedule rules only."
)
"""Exact limitation note required by the Phase 6 what-if contract."""

_CLOSED_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.completed, TaskStatus.cancelled}
)
"""Tasks that no longer reserve schedule time."""

_PROTECTED_CATEGORIES: frozenset[TaskCategory] = SLEEP_CATEGORIES | RECOVERY_CATEGORIES
"""Categories that count as sleep or recovery opportunity, not busy work."""

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.critical: 4,
    Severity.high: 3,
    Severity.medium: 2,
    Severity.low: 1,
}

_METRIC_CONFIG_KEYS: tuple[str, ...] = (
    "CONFLICT_OVERLAP_TOLERANCE_MINUTES",
    "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
    "DEMANDING_WORKLOAD_LEVELS",
    "MAX_DEMANDING_TASKS_PER_WINDOW",
    "MAX_DEMANDING_TASK_HOURS_PER_WINDOW",
    "MIN_RECOVERY_GAP_MINUTES",
    "SLEEP_SHORTFALL_REVIEW_RATIO",
    "WORKLOAD_WINDOW_HOURS",
)
"""Configuration keys that the comparison metrics depend on."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _require_aware(value: datetime, label: str) -> datetime:
    """Require an aware datetime and normalise it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware (UTC)")
    return value.astimezone(timezone.utc)


def _is_open(task: TaskView) -> bool:
    """Return True for a task that is still upcoming."""
    return task.status not in _CLOSED_STATUSES


def _is_demanding(task: TaskView, config: MissionConfig) -> bool:
    """Return True when a task demands high alertness or is critical.

    This mirrors ``conflicts._is_demanding`` so workload metrics and the
    conflict rule use the same definition.
    """
    if task.is_critical or task.priority is Priority.critical:
        return True
    if task.workload_level in config.DEMANDING_WORKLOAD_LEVELS:
        return True
    return (
        task.required_alertness is not None
        and task.required_alertness >= config.CRITICAL_TASK_ALERTNESS_REQUIREMENT
    )


def _is_protected(task: TaskView) -> bool:
    """Return True for sleep, rest, and recovery tasks."""
    return task.category in _PROTECTED_CATEGORIES


def _sort_key(task: TaskView) -> tuple[datetime, str]:
    """Order tasks by start time, then id for deterministic output."""
    return task.start_time, task.task_id


def _replace_task(context: AstronautContext, updated: TaskView) -> AstronautContext:
    """Return a copied context with one task replaced by ``updated``."""
    tasks = [
        updated if task.task_id == updated.task_id else task
        for task in context.tasks
    ]
    return context.model_copy(update={"tasks": tasks})


def _with_tasks(
    context: AstronautContext, tasks: Sequence[TaskView]
) -> AstronautContext:
    """Return a copied context with a new task list."""
    return context.model_copy(update={"tasks": list(tasks)})


def _require_task(context: AstronautContext, task_id: str) -> TaskView:
    """Return an open task that belongs to the context's crew.

    Raises:
        ValueError: if the task id is unknown, belongs to another astronaut, or
            the task is completed/cancelled.
    """
    for task in context.tasks:
        if task.task_id != task_id:
            continue
        if task.astronaut_id != context.crew.crew_id:
            raise ValueError(
                f"task {task_id!r} belongs to {task.astronaut_id!r}, not "
                f"{context.crew.crew_id!r}"
            )
        if not _is_open(task):
            raise ValueError(
                f"task {task_id!r} has status {task.status.value!r} and cannot "
                "be rescheduled"
            )
        return task
    raise ValueError(
        f"task {task_id!r} was not found in the context for "
        f"{context.crew.crew_id!r}"
    )


def _overlap_minutes(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> int:
    """Return the whole-minute overlap of two intervals (0 when disjoint)."""
    start = max(first_start, second_start)
    end = min(first_end, second_end)
    if end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


def _interval_minutes(start: datetime, end: datetime) -> int:
    """Return the whole-minute length of an interval (never negative)."""
    return max(0, int((end - start).total_seconds() // 60))


def _merge_intervals(
    intervals: Sequence[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Merge overlapping or touching intervals into a sorted list."""
    ordered = sorted(intervals)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _recovery_task_id(
    *,
    astronaut_id: str,
    start: datetime,
    end: datetime,
    sequence: int,
) -> str:
    """Build a deterministic id for an inserted recovery task.

    The hash covers the astronaut, the interval, and the number of recovery
    tasks already present, so adding the same interval twice still produces
    distinct ids while repeated calls on the same context are stable.
    """
    payload = "|".join(
        (
            astronaut_id,
            start.isoformat(),
            end.isoformat(),
            str(sequence),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"rec_{digest}"


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def delay_task(
    context: AstronautContext,
    task_id: str,
    minutes: int,
) -> AstronautContext:
    """Return a copy of ``context`` with one task shifted later.

    Both ``start_time`` and ``end_time`` move by the same amount, so the task
    duration is preserved. Other tasks are not moved; any resulting overlap is
    left for :func:`compare` to report.

    Raises:
        ValueError: if the task is unknown, belongs to another astronaut, is
            closed, or ``minutes`` is not positive.
    """
    if not isinstance(minutes, int) or isinstance(minutes, bool):
        raise ValueError("minutes must be an integer")
    if minutes <= 0:
        raise ValueError("minutes must be positive; use move_task to reschedule")
    task = _require_task(context, task_id)
    delta = timedelta(minutes=minutes)
    updated = task.model_copy(
        update={
            "start_time": task.start_time + delta,
            "end_time": task.end_time + delta,
        }
    )
    return _replace_task(context, updated)


def move_task(
    context: AstronautContext,
    task_id: str,
    new_start: datetime,
) -> AstronautContext:
    """Return a copy of ``context`` with one task moved to ``new_start``.

    The task duration is preserved. Other tasks are not moved, so a move into an
    occupied slot is allowed and will be reported by :func:`compare` as an
    overlap.

    Raises:
        ValueError: if the task is unknown, belongs to another astronaut, is
            closed, or ``new_start`` is naive.
    """
    start = _require_aware(new_start, "new_start")
    task = _require_task(context, task_id)
    duration = task.end_time - task.start_time
    updated = task.model_copy(
        update={"start_time": start, "end_time": start + duration}
    )
    return _replace_task(context, updated)


def add_recovery_period(
    context: AstronautContext,
    start: datetime,
    end: datetime,
    *,
    shift_following_tasks: bool = True,
    task_id: str | None = None,
    name: str = "Structured recovery period",
) -> AstronautContext:
    """Return a copy of ``context`` with an inserted recovery block.

    The new task has category ``rest_recovery``, low workload, low priority, and
    no required alertness, so it is treated as recovery opportunity by the
    Phase 4 rules.

    With ``shift_following_tasks=True`` (the default) the block is inserted into
    the timeline: every open task starting at or after ``start`` is pushed
    forward by the block duration. This is what makes the operation meaningful
    for ``R-RECOVERY-01``/``R-RECOVERY-02``: those rules measure *free* time,
    and sleep/rest/recovery tasks are already treated as free opportunity, so a
    block merely overlapped with work would not create a recovery gap.

    With ``shift_following_tasks=False`` the block is added without rescheduling
    anything. That is a pure edit, but it may overlap existing tasks.

    Raises:
        ValueError: if either datetime is naive, ``end`` is not after ``start``,
            the insertion point splits a task that began earlier, or the
            supplied ``task_id`` already exists.
    """
    block_start = _require_aware(start, "start")
    block_end = _require_aware(end, "end")
    if block_end <= block_start:
        raise ValueError("end must be after start")

    if task_id is not None and any(
        task.task_id == task_id for task in context.tasks
    ):
        raise ValueError(f"task {task_id!r} already exists")

    if shift_following_tasks:
        for task in context.tasks:
            if not _is_open(task):
                continue
            if task.start_time < block_start < task.end_time:
                raise ValueError(
                    f"the recovery period starts inside task {task.task_id!r}; "
                    "choose a boundary between tasks"
                )

    duration = block_end - block_start
    tasks: list[TaskView] = []
    for task in context.tasks:
        if (
            shift_following_tasks
            and _is_open(task)
            and task.start_time >= block_start
        ):
            tasks.append(
                task.model_copy(
                    update={
                        "start_time": task.start_time + duration,
                        "end_time": task.end_time + duration,
                    }
                )
            )
        else:
            tasks.append(task)

    sequence = sum(
        1
        for task in context.tasks
        if task.category in RECOVERY_CATEGORIES
        and task.start_time == block_start
        and task.end_time == block_end
    )
    new_id = task_id or _recovery_task_id(
        astronaut_id=context.crew.crew_id,
        start=block_start,
        end=block_end,
        sequence=sequence,
    )
    tasks.append(
        TaskView(
            task_id=new_id,
            astronaut_id=context.crew.crew_id,
            name=name,
            category=TaskCategory.rest_recovery,
            start_time=block_start,
            end_time=block_end,
            priority=Priority.low,
            workload_level=WorkloadLevel.low,
            required_alertness=None,
            status=TaskStatus.planned,
            is_critical=False,
        )
    )
    return _with_tasks(context, tasks)


def redistribute_workload(
    context: AstronautContext,
    task_id: str,
    new_start: datetime,
    config: MissionConfig = DEFAULT_CONFIG,
) -> AstronautContext:
    """Move one demanding task to a different slot.

    This is :func:`move_task` with an extra guard: only a demanding task may be
    redistributed, using the same definition as ``R-WORKLOAD-01``.

    Raises:
        ValueError: if the task is unknown, closed, belongs to another
            astronaut, is not demanding, or ``new_start`` is naive.
    """
    task = _require_task(context, task_id)
    if not _is_demanding(task, config):
        raise ValueError(
            f"task {task_id!r} is not demanding under DEMANDING_WORKLOAD_LEVELS "
            "and CRITICAL_TASK_ALERTNESS_REQUIREMENT"
        )
    return move_task(context, task_id, new_start)


def modify_sleep_window(
    context: AstronautContext,
    new_start: datetime,
    new_end: datetime,
    *,
    window_index: int = 0,
) -> AstronautContext:
    """Return a copy of ``context`` with one sleep window replaced.

    The window's ``source`` is preserved: a what-if edit must not invent a new
    provenance for the window.

    Raises:
        ValueError: if the index is out of range, either datetime is naive, or
            ``new_end`` is not after ``new_start``.
    """
    windows = list(context.planned_sleep_windows)
    if not windows:
        raise ValueError("the context has no planned or inferred sleep window")
    if not isinstance(window_index, int) or isinstance(window_index, bool):
        raise ValueError("window_index must be an integer")
    if not 0 <= window_index < len(windows):
        raise ValueError(
            f"window_index {window_index} is out of range for "
            f"{len(windows)} sleep window(s)"
        )

    start = _require_aware(new_start, "new_start")
    end = _require_aware(new_end, "new_end")
    if end <= start:
        raise ValueError("new_end must be after new_start")

    windows[window_index] = windows[window_index].model_copy(
        update={"start_time": start, "end_time": end}
    )
    return context.model_copy(update={"planned_sleep_windows": windows})


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _conflict_metrics(
    report: ConflictReport,
) -> tuple[list[ConflictTypeMetric], int, Severity | None]:
    """Aggregate a conflict report by type and return (metrics, count, top)."""
    grouped: dict[ConflictType, list[Conflict]] = {}
    for conflict in report.conflicts:
        grouped.setdefault(conflict.conflict_type, []).append(conflict)

    metrics: list[ConflictTypeMetric] = []
    for conflict_type in ConflictType:
        items = grouped.get(conflict_type)
        if not items:
            continue
        severity_counts: dict[Severity, int] = {}
        for severity in Severity:
            count = sum(1 for conflict in items if conflict.severity is severity)
            if count:
                severity_counts[severity] = count
        highest = max(items, key=lambda conflict: _SEVERITY_RANK[conflict.severity])
        metrics.append(
            ConflictTypeMetric(
                conflict_type=conflict_type,
                count=len(items),
                highest_severity=highest.severity,
                severity_counts=severity_counts,
            )
        )

    if not report.conflicts:
        return metrics, 0, None
    highest = max(
        (conflict.severity for conflict in report.conflicts),
        key=lambda severity: _SEVERITY_RANK[severity],
    )
    return metrics, len(report.conflicts), highest


def _workload_windows(
    context: AstronautContext,
    config: MissionConfig,
) -> list[WorkloadWindowMetric]:
    """Return the maximal workload windows used by ``R-WORKLOAD-01``.

    The logic mirrors the rule: a window starts at each demanding task and spans
    ``WORKLOAD_WINDOW_HOURS``; a task is counted when it starts inside the
    window; a window whose task set is a subset of an already-reported set is
    skipped. Unlike the rule, every window is returned, including ones that do
    not exceed a configured limit, so a comparison can show the full workload
    distribution.
    """
    demanding = sorted(
        (
            task
            for task in context.tasks
            if _is_open(task) and _is_demanding(task, config)
        ),
        key=_sort_key,
    )
    span = timedelta(hours=config.WORKLOAD_WINDOW_HOURS)
    reported: list[frozenset[str]] = []
    metrics: list[WorkloadWindowMetric] = []

    for anchor in demanding:
        window_start = anchor.start_time
        window_end = window_start + span
        group = [
            task
            for task in demanding
            if window_start <= task.start_time < window_end
        ]
        task_ids = frozenset(task.task_id for task in group)
        if any(task_ids <= seen for seen in reported):
            continue
        reported.append(task_ids)

        demanding_minutes = sum(
            _overlap_minutes(
                task.start_time, task.end_time, window_start, window_end
            )
            for task in group
        )
        metrics.append(
            WorkloadWindowMetric(
                window_start=window_start,
                window_end=window_end,
                demanding_task_count=len(group),
                demanding_minutes=demanding_minutes,
                exceeds_task_limit=(
                    len(group) > config.MAX_DEMANDING_TASKS_PER_WINDOW
                ),
                exceeds_minutes_limit=(
                    demanding_minutes
                    > config.MAX_DEMANDING_TASK_HOURS_PER_WINDOW
                ),
                task_ids=[task.task_id for task in group],
            )
        )
    return metrics


def _total_recovery_minutes(
    context: AstronautContext, window_start: datetime, window_end: datetime
) -> int:
    """Return merged recovery-category minutes inside the evaluation window."""
    intervals: list[tuple[datetime, datetime]] = []
    for task in context.tasks:
        if not _is_open(task) or task.category not in RECOVERY_CATEGORIES:
            continue
        clipped_start = max(task.start_time, window_start)
        clipped_end = min(task.end_time, window_end)
        if clipped_end > clipped_start:
            intervals.append((clipped_start, clipped_end))
    return sum(
        _interval_minutes(start, end) for start, end in _merge_intervals(intervals)
    )


def _longest_recovery_gap(
    context: AstronautContext, window_start: datetime, window_end: datetime
) -> int:
    """Return the longest interval with no non-protected open task.

    Sleep, rest, and recovery tasks are treated as recovery opportunity, which
    matches the free-time definition used by the recovery rules.
    """
    busy: list[tuple[datetime, datetime]] = []
    for task in context.tasks:
        if not _is_open(task) or _is_protected(task):
            continue
        clipped_start = max(task.start_time, window_start)
        clipped_end = min(task.end_time, window_end)
        if clipped_end > clipped_start:
            busy.append((clipped_start, clipped_end))

    longest = 0
    cursor = window_start
    for start, end in _merge_intervals(busy):
        if start > cursor:
            longest = max(longest, _interval_minutes(cursor, start))
        cursor = max(cursor, end)
    if window_end > cursor:
        longest = max(longest, _interval_minutes(cursor, window_end))
    return longest


def _tasks_inside_sleep_windows(
    context: AstronautContext, config: MissionConfig
) -> list[str]:
    """Return open wake tasks that overlap a sleep window beyond tolerance.

    This mirrors the trigger of ``R-SLEEP-WINDOW-01``. A task is listed once
    even when it overlaps several windows.
    """
    tolerance = config.CONFLICT_OVERLAP_TOLERANCE_MINUTES
    inside: list[TaskView] = []
    for task in context.tasks:
        if not _is_open(task) or _is_protected(task):
            continue
        if any(
            _overlap_minutes(
                task.start_time,
                task.end_time,
                window.start_time,
                window.end_time,
            )
            > tolerance
            for window in context.planned_sleep_windows
        ):
            inside.append(task)
    inside.sort(key=_sort_key)
    return [task.task_id for task in inside]


def _schedule_metrics(
    context: AstronautContext,
    window_start: datetime,
    window_end: datetime,
    *,
    fatigue_level: FatigueLevel,
    fatigue_source: str,
    config: MissionConfig,
    report: ConflictReport | None = None,
) -> ScheduleMetrics:
    """Build the rule-based metrics for one schedule."""
    if report is None:
        report = detect_conflicts(context, config)
    conflicts_by_type, total_conflicts, highest_severity = _conflict_metrics(report)
    gaps = free_gaps(
        [task for task in context.tasks if _is_open(task)],
        window_start,
        window_end,
        config,
        min_minutes=0,
    )
    total_free = sum(gap.duration_minutes for gap in gaps)
    total_recovery = _total_recovery_minutes(context, window_start, window_end)
    inside = _tasks_inside_sleep_windows(context, config)

    return ScheduleMetrics(
        evaluation_start=window_start,
        evaluation_end=window_end,
        conflicts_by_type=conflicts_by_type,
        total_conflicts=total_conflicts,
        highest_severity=highest_severity,
        workload_windows=_workload_windows(context, config),
        total_free_minutes=total_free,
        total_recovery_minutes=total_recovery,
        total_recovery_and_free_minutes=total_free + total_recovery,
        longest_recovery_gap_minutes=_longest_recovery_gap(
            context, window_start, window_end
        ),
        tasks_inside_sleep_windows=len(inside),
        task_ids_inside_sleep_windows=inside,
        fatigue_level=fatigue_level,
        fatigue_source=fatigue_source,
        data_warning_count=len(report.data_warnings),
        data_warning_rule_ids=sorted(
            {warning.rule_id for warning in report.data_warnings}
        ),
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _auto_window(context: AstronautContext) -> tuple[datetime, datetime]:
    """Derive the evaluation window from open tasks and sleep windows.

    The window starts at the earliest boundary and ends at the latest boundary
    in the original context. Task lists are flattened first so a missing
    boundary is an explicit error rather than an invented default.
    """
    starts: list[datetime] = []
    ends: list[datetime] = []
    for task in context.tasks:
        if _is_open(task):
            starts.append(task.start_time)
            ends.append(task.end_time)
    for window in context.planned_sleep_windows:
        starts.append(window.start_time)
        ends.append(window.end_time)
    if not starts:
        raise ValueError(
            "cannot derive an evaluation window: the original context has no "
            "open task or sleep window"
        )
    return min(starts), max(ends)


def _validate_pair(
    original: AstronautContext, proposed: AstronautContext
) -> None:
    """Reject a comparison that would change non-schedule inputs."""
    if original.crew.crew_id != proposed.crew.crew_id:
        raise ValueError(
            "original and proposed contexts belong to different astronauts: "
            f"{original.crew.crew_id!r} and {proposed.crew.crew_id!r}"
        )
    if original.crew != proposed.crew:
        raise ValueError("original and proposed contexts must share a crew profile")
    if original.recent_sleep != proposed.recent_sleep:
        raise ValueError(
            "original and proposed contexts must share the same recent sleep "
            "history; fatigue is not re-predicted"
        )
    if original.fatigue_signal != proposed.fatigue_signal:
        raise ValueError(
            "original and proposed contexts must share the same fatigue signal; "
            "fatigue is not re-predicted"
        )


def _summary(
    original: ScheduleMetrics,
    proposed: ScheduleMetrics,
    resolved: Sequence[Conflict],
    new: Sequence[Conflict],
) -> str:
    """Build a rule-only comparison summary with the required wording."""
    delta = proposed.total_conflicts - original.total_conflicts
    if delta < 0:
        count_text = (
            f"The proposed schedule has {abs(delta)} fewer conflicts under the "
            "configured rules than the original schedule"
        )
    elif delta > 0:
        count_text = (
            f"The proposed schedule has {delta} more conflicts under the "
            "configured rules than the original schedule"
        )
    else:
        count_text = (
            "Both schedules have the same number of conflicts under the "
            "configured rules"
        )

    conflict_text = (
        f" ({original.total_conflicts} original, {proposed.total_conflicts} "
        f"proposed; {len(resolved)} resolved and {len(new)} new conflict(s))."
    )
    schedule_text = (
        f" Free time is {original.total_free_minutes} min original vs "
        f"{proposed.total_free_minutes} min proposed; recovery time is "
        f"{original.total_recovery_minutes} min vs "
        f"{proposed.total_recovery_minutes} min; the longest recovery gap is "
        f"{original.longest_recovery_gap_minutes} min vs "
        f"{proposed.longest_recovery_gap_minutes} min. These are rule-based "
        "schedule metrics, not a fatigue prediction."
    )
    return count_text + conflict_text + schedule_text


def compare(
    original: AstronautContext,
    proposed: AstronautContext,
    config: MissionConfig = DEFAULT_CONFIG,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> ScenarioComparison:
    """Compare an original and a proposed schedule using schedule rules only.

    Both contexts must describe the same astronaut, crew profile, recent sleep
    history, and fatigue signal. Only the schedule may differ. This guard keeps
    the comparison honest: the method cannot accidentally present a fatigue
    change as a schedule effect, because fatigue is copied unchanged into both
    metric sets.

    The evaluation window defaults to the earliest and latest boundary among the
    original context's open tasks and sleep windows. An explicit
    ``window_start``/``window_end`` pair overrides it; supplying only one of the
    two is an error. The same window is used for both schedules.

    Args:
        original: The baseline context.
        proposed: The context returned by a scenario operation.
        config: Immutable threshold set.
        window_start: Optional explicit evaluation start (UTC-aware).
        window_end: Optional explicit evaluation end (UTC-aware).

    Returns:
        A deterministic ``ScenarioComparison``. ``resolved_conflicts`` are
        original conflicts whose deterministic id is absent from the proposed
        report; ``new_conflicts`` are the reverse. ``note`` is the exact
        ``FATIGUE_NOTE`` statement.

    Raises:
        ValueError: if the contexts differ in crew, sleep history, or fatigue
            signal; if the window is invalid; or if no window can be derived.
    """
    _validate_pair(original, proposed)

    if (window_start is None) != (window_end is None):
        raise ValueError("window_start and window_end must be supplied together")
    if window_start is None:
        start, end = _auto_window(original)
    else:
        if window_end is None:  # pragma: no cover - guarded by the check above
            raise ValueError("window_start and window_end must be supplied together")
        start = _require_aware(window_start, "window_start")
        end = _require_aware(window_end, "window_end")
        if end <= start:
            raise ValueError("window_end must be after window_start")

    fatigue_level = original.fatigue_signal.level
    fatigue_source = original.fatigue_signal.source
    original_report = detect_conflicts(original, config)
    proposed_report = detect_conflicts(proposed, config)
    original_metrics = _schedule_metrics(
        original,
        start,
        end,
        fatigue_level=fatigue_level,
        fatigue_source=fatigue_source,
        config=config,
        report=original_report,
    )
    proposed_metrics = _schedule_metrics(
        proposed,
        start,
        end,
        fatigue_level=fatigue_level,
        fatigue_source=fatigue_source,
        config=config,
        report=proposed_report,
    )

    original_ids = {conflict.conflict_id for conflict in original_report.conflicts}
    proposed_ids = {conflict.conflict_id for conflict in proposed_report.conflicts}
    resolved = [
        conflict
        for conflict in original_report.conflicts
        if conflict.conflict_id not in proposed_ids
    ]
    new = [
        conflict
        for conflict in proposed_report.conflicts
        if conflict.conflict_id not in original_ids
    ]

    config_keys = sorted(
        set(_METRIC_CONFIG_KEYS)
        | set(original_report.config_keys)
        | set(proposed_report.config_keys)
    )
    return ScenarioComparison(
        original_metrics=original_metrics,
        proposed_metrics=proposed_metrics,
        conflict_count_delta=(
            proposed_metrics.total_conflicts - original_metrics.total_conflicts
        ),
        resolved_conflicts=resolved,
        new_conflicts=new,
        summary=_summary(original_metrics, proposed_metrics, resolved, new),
        note=FATIGUE_NOTE,
        config_keys=config_keys,
    )
