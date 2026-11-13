"""Rule-based schedule conflict detection for mission intelligence.

Every public rule function is pure: it takes an ``AstronautContext`` and returns
a ``RuleOutcome`` containing zero or more ``Conflict`` objects and, when a rule
cannot be evaluated, zero or more ``DataWarning`` objects. No database session is
imported here, and no state is mutated.

Rule ids (proposed system logic, Phase 4):

* ``R-SLEEP-WINDOW-01`` - a wake task overlaps a planned/inferred sleep window.
* ``R-RECOVERY-01`` - too little free recovery time between two demanding tasks.
* ``R-RECOVERY-02`` - too little free recovery time after a short recorded sleep
  before a demanding task.
* ``R-FATIGUE-CRITICAL-01`` - monitor/elevated fatigue before a critical or
  high-alertness task.
* ``R-WORKLOAD-01`` - too many demanding tasks, or too many demanding minutes,
  inside one workload window.
* ``R-CIRCADIAN-01`` - a wake task falls inside the habitual sleep period or the
  configured Window of Circadian Low (WOCL).

Missing-data rule ids used in ``DataWarning``:

* ``R-FATIGUE-DATA-01`` - fatigue is ``unknown``, so R-FATIGUE-CRITICAL-01 is
  skipped for that task.
* ``R-DATA-SLEEP-WINDOW`` - no planned/inferred sleep window is available.
* ``R-DATA-SLEEP-RECORD`` - no recent sleep record is available.

Every numeric threshold comes from ``MissionConfig``. The sources in
``docs/01_references.md`` support the concepts (sleep opportunity, recovery,
circadian trough, workload) but state no numbers, so all values are configurable
assumptions, never NASA cut-offs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Collection, Sequence

from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.models import (
    AstronautContext,
    Conflict,
    ConflictReport,
    ConflictType,
    DataWarning,
    FatigueLevel,
    Priority,
    Severity,
    TaskCategory,
    TaskStatus,
    TaskView,
)
from app.mission.schedule import RECOVERY_CATEGORIES, SLEEP_CATEGORIES

RULE_SET_VERSION = "mission-conflicts/1.0"
"""Version tag recorded in every ``ConflictReport`` for traceability."""

CLOSED_TASK_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.completed, TaskStatus.cancelled}
)
"""Tasks that are no longer upcoming and are therefore not evaluated."""

PROTECTED_SLEEP_TASK_CATEGORIES: frozenset[TaskCategory] = (
    SLEEP_CATEGORIES | RECOVERY_CATEGORIES
)
"""Categories allowed to occupy a sleep or recovery interval."""

_MINUTES_PER_DAY = 24 * 60

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.critical: 4,
    Severity.high: 3,
    Severity.medium: 2,
    Severity.low: 1,
}


@dataclass(frozen=True)
class RuleOutcome:
    """Conflicts and data warnings produced by one rule function."""

    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[DataWarning] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _sort_key(task: TaskView) -> tuple[datetime, str]:
    """Order tasks by start time, then id for deterministic output."""
    return task.start_time, task.task_id


def _is_open(task: TaskView) -> bool:
    """Return True for a task that is still upcoming."""
    return task.status not in CLOSED_TASK_STATUSES


def _is_demanding(task: TaskView, config: MissionConfig) -> bool:
    """Return True when a task demands high alertness or is critical.

    This mirrors ``integration._is_demanding`` so both modules apply the same
    definition. The test is deliberately broad: critical flag, critical
    priority, a configured demanding workload level, or a required alertness at
    or above ``CRITICAL_TASK_ALERTNESS_REQUIREMENT``.
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
    """Return True for sleep/rest/recovery tasks."""
    return task.category in PROTECTED_SLEEP_TASK_CATEGORIES


def _latest_sleep(context: AstronautContext):
    """Return the most recent sleep summary, or ``None`` when there is none."""
    return max(
        context.recent_sleep,
        key=lambda summary: (summary.end_time, summary.sleep_id),
        default=None,
    )


def _target_minutes(context: AstronautContext) -> int:
    """Return the crew sleep target in whole minutes (may be non-positive)."""
    return int(round(context.crew.sleep_target_hours * 60))


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


def _free_minutes_between(
    tasks: Collection[TaskView], start: datetime, end: datetime
) -> int:
    """Return unused minutes in ``[start, end)`` after merging other tasks.

    Sleep, rest, and recovery tasks are treated as recovery opportunity and are
    not counted as busy time. Overlapping work is merged so it is never counted
    twice.
    """
    if end <= start:
        return 0
    total = int((end - start).total_seconds() // 60)
    busy: list[tuple[datetime, datetime]] = []
    for task in tasks:
        if _is_protected(task):
            continue
        clipped_start = max(task.start_time, start)
        clipped_end = min(task.end_time, end)
        if clipped_end > clipped_start:
            busy.append((clipped_start, clipped_end))
    busy.sort()
    merged: list[tuple[datetime, datetime]] = []
    for busy_start, busy_end in busy:
        if merged and busy_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], busy_end))
        else:
            merged.append((busy_start, busy_end))
    busy_minutes = sum(
        int((busy_end - busy_start).total_seconds() // 60)
        for busy_start, busy_end in merged
    )
    return max(0, total - busy_minutes)


def _severity_for_task(task: TaskView) -> Severity:
    """Return a base severity: critical task, high alertness, or medium."""
    if task.is_critical or task.priority is Priority.critical:
        return Severity.critical
    return Severity.high


def _sorted_keys(keys: Sequence[str]) -> list[str]:
    """Return unique configuration keys in a stable order."""
    return sorted(dict.fromkeys(keys))


def _conflict_id(
    *,
    astronaut_id: str,
    task_ids: Sequence[str],
    conflict_type: ConflictType,
    rule_id: str,
    affected_start: datetime,
    affected_end: datetime,
) -> str:
    """Build a deterministic conflict id from the inputs that define it.

    The hash covers the astronaut, the sorted involved task ids, the conflict
    type, the rule id, and the affected interval. Re-evaluating the same inputs
    therefore produces the same id, while a different window or rule produces a
    different one.
    """
    payload = "|".join(
        (
            astronaut_id,
            ",".join(sorted(task_ids)),
            conflict_type.value,
            rule_id,
            affected_start.isoformat(),
            affected_end.isoformat(),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"cf_{digest}"


def _build_conflict(
    *,
    rule_id: str,
    conflict_type: ConflictType,
    severity: Severity,
    astronaut_id: str,
    task_ids: Sequence[str],
    affected_start: datetime,
    affected_end: datetime,
    explanation: str,
    suggested_action: str,
    source_ids: Sequence[str] = (),
    config_keys: Sequence[str] = (),
) -> Conflict:
    """Assemble a ``Conflict`` with a deterministic id."""
    return Conflict(
        conflict_id=_conflict_id(
            astronaut_id=astronaut_id,
            task_ids=task_ids,
            conflict_type=conflict_type,
            rule_id=rule_id,
            affected_start=affected_start,
            affected_end=affected_end,
        ),
        rule_id=rule_id,
        conflict_type=conflict_type,
        severity=severity,
        astronaut_id=astronaut_id,
        task_ids=list(task_ids),
        affected_start=affected_start,
        affected_end=affected_end,
        explanation=explanation,
        suggested_action=suggested_action,
        source_ids=list(source_ids),
        config_keys=_sorted_keys(config_keys),
    )


def _percent(ratio: float) -> str:
    """Format a ratio as a whole percentage."""
    return f"{ratio * 100:.0f}%"


# ---------------------------------------------------------------------------
# Rule 1: sleep_mission_conflict
# ---------------------------------------------------------------------------


def sleep_mission_conflict(
    context: AstronautContext,
    task: TaskView,
    config: MissionConfig = DEFAULT_CONFIG,
) -> RuleOutcome:
    """Flag a wake task that overlaps a planned or inferred sleep window.

    Sleep, rest, and recovery tasks are exempt because occupying a sleep window
    is their purpose. The configured ``CONFLICT_OVERLAP_TOLERANCE_MINUTES``
    suppresses overlaps at or below the tolerance; the default is zero, so any
    positive overlap is a conflict.
    """
    if _is_protected(task):
        return RuleOutcome()

    tolerance = config.CONFLICT_OVERLAP_TOLERANCE_MINUTES
    conflicts: list[Conflict] = []
    for window in context.planned_sleep_windows:
        overlap = _overlap_minutes(
            task.start_time, task.end_time, window.start_time, window.end_time
        )
        if overlap <= tolerance:
            continue
        affected_start = max(task.start_time, window.start_time)
        affected_end = min(task.end_time, window.end_time)
        severity = _severity_for_task(task)
        explanation = (
            f"Rule R-SLEEP-WINDOW-01: task '{task.task_id}' ({task.name}) runs "
            f"{task.start_time.isoformat()} to {task.end_time.isoformat()} and "
            f"overlaps the planned sleep window {window.start_time.isoformat()} "
            f"to {window.end_time.isoformat()} ({window.source}) by {overlap} "
            f"min. The configured overlap tolerance is {tolerance} min."
        )
        suggested_action = (
            "Review moving this task or adjusting the sleep window under rule "
            "R-SLEEP-WINDOW-01; protecting the sleep opportunity may reduce risk. "
            "Advisory only; mission and medical approval remain required."
        )
        conflicts.append(
            _build_conflict(
                rule_id="R-SLEEP-WINDOW-01",
                conflict_type=ConflictType.sleep_window_conflict,
                severity=severity,
                astronaut_id=task.astronaut_id,
                task_ids=[task.task_id],
                affected_start=affected_start,
                affected_end=affected_end,
                explanation=explanation,
                suggested_action=suggested_action,
                source_ids=["NASA-HRP-Sleep-Risk", "NASA-STD-3001-Vol2"],
                config_keys=["CONFLICT_OVERLAP_TOLERANCE_MINUTES"],
            )
        )
    return RuleOutcome(conflicts=conflicts)


# ---------------------------------------------------------------------------
# Rule 2: insufficient_recovery
# ---------------------------------------------------------------------------


def insufficient_recovery(
    context: AstronautContext,
    task: TaskView,
    config: MissionConfig = DEFAULT_CONFIG,
) -> RuleOutcome:
    """Flag too little free recovery around a demanding task.

    Two triggers are implemented:

    * ``R-RECOVERY-01``: the free time between the end of the previous demanding
      task and the start of this demanding task is below
      ``MIN_RECOVERY_GAP_MINUTES``.
    * ``R-RECOVERY-02``: the latest recorded sleep is below
      ``SLEEP_SHORTFALL_REVIEW_RATIO`` of the target and the free time between
      the end of that sleep and this demanding task is below
      ``MIN_RECOVERY_GAP_MINUTES``.

    "Free time" excludes other work but counts sleep/rest/recovery tasks as
    recovery opportunity. Non-demanding tasks do not trigger either rule.
    """
    if _is_protected(task) or not _is_demanding(task, config):
        return RuleOutcome()

    others = [
        item
        for item in context.tasks
        if item.task_id != task.task_id
        and item.astronaut_id == task.astronaut_id
        and _is_open(item)
    ]
    conflicts: list[Conflict] = []
    severity = _severity_for_task(task)
    base_keys = (
        "MIN_RECOVERY_GAP_MINUTES",
        "DEMANDING_WORKLOAD_LEVELS",
        "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
    )

    previous_demanding = [
        item
        for item in others
        if _is_demanding(item, config) and item.end_time <= task.start_time
    ]
    if previous_demanding:
        previous = max(previous_demanding, key=_sort_key)
        free = _free_minutes_between(others, previous.end_time, task.start_time)
        if free < config.MIN_RECOVERY_GAP_MINUTES:
            explanation = (
                f"Rule R-RECOVERY-01: demanding task '{task.task_id}' starts at "
                f"{task.start_time.isoformat()}, only {free} free min after "
                f"demanding task '{previous.task_id}' ends at "
                f"{previous.end_time.isoformat()}. The configured minimum "
                f"recovery gap is {config.MIN_RECOVERY_GAP_MINUTES} min."
            )
            suggested_action = (
                "Review inserting a structured recovery break or moving one of "
                "the demanding tasks under rule R-RECOVERY-01; a recovery gap may "
                "reduce risk. Advisory only."
            )
            conflicts.append(
                _build_conflict(
                    rule_id="R-RECOVERY-01",
                    conflict_type=ConflictType.insufficient_recovery_gap,
                    severity=severity,
                    astronaut_id=task.astronaut_id,
                    task_ids=[previous.task_id, task.task_id],
                    affected_start=previous.end_time,
                    affected_end=task.start_time,
                    explanation=explanation,
                    suggested_action=suggested_action,
                    source_ids=[
                        "NASA-TM-Fatigue-Countermeasures",
                        "NASA-STD-3001-Vol2",
                    ],
                    config_keys=base_keys,
                )
            )

    latest_sleep = _latest_sleep(context)
    target_minutes = _target_minutes(context)
    if (
        latest_sleep is not None
        and target_minutes > 0
        and task.start_time >= latest_sleep.end_time
    ):
        ratio = latest_sleep.duration_minutes / target_minutes
        if ratio < config.SLEEP_SHORTFALL_REVIEW_RATIO:
            free = _free_minutes_between(others, latest_sleep.end_time, task.start_time)
            if free < config.MIN_RECOVERY_GAP_MINUTES:
                explanation = (
                    f"Rule R-RECOVERY-02: latest sleep is "
                    f"{latest_sleep.duration_minutes} min, {_percent(ratio)} of the "
                    f"{target_minutes} min target and below the "
                    f"{_percent(config.SLEEP_SHORTFALL_REVIEW_RATIO)} review ratio. "
                    f"Demanding task '{task.task_id}' starts at "
                    f"{task.start_time.isoformat()}, only {free} free min after "
                    f"sleep ends at {latest_sleep.end_time.isoformat()}. The "
                    f"configured minimum recovery gap is "
                    f"{config.MIN_RECOVERY_GAP_MINUTES} min."
                )
                suggested_action = (
                    "Review adding a recovery or rest opportunity before this "
                    "demanding task under rule R-RECOVERY-02; it may reduce risk. "
                    "Advisory only; extended sleep decisions remain with the crew "
                    "and flight surgeon."
                )
                conflicts.append(
                    _build_conflict(
                        rule_id="R-RECOVERY-02",
                        conflict_type=ConflictType.insufficient_recovery_gap,
                        severity=severity,
                        astronaut_id=task.astronaut_id,
                        task_ids=[task.task_id],
                        affected_start=latest_sleep.end_time,
                        affected_end=task.start_time,
                        explanation=explanation,
                        suggested_action=suggested_action,
                        source_ids=[
                            "NASA-TM-Fatigue-Countermeasures",
                            "NASA-STD-3001-Vol2",
                        ],
                        config_keys=base_keys + ("SLEEP_SHORTFALL_REVIEW_RATIO",),
                    )
                )

    return RuleOutcome(conflicts=conflicts)


# ---------------------------------------------------------------------------
# Rule 3: high_fatigue_before_critical
# ---------------------------------------------------------------------------


def high_fatigue_before_critical(
    context: AstronautContext,
    task: TaskView,
    config: MissionConfig = DEFAULT_CONFIG,
) -> RuleOutcome:
    """Flag monitor/elevated fatigue before a critical or high-alertness task.

    ``unknown`` fatigue never raises a conflict. It returns a
    ``R-FATIGUE-DATA-01`` warning instead, so the caller can see that no
    judgement was made. A ``no_flag`` signal does not trigger the rule.
    """
    critical = (
        task.is_critical
        or task.priority is Priority.critical
        or (
            task.required_alertness is not None
            and task.required_alertness >= config.CRITICAL_TASK_ALERTNESS_REQUIREMENT
        )
    )
    if not critical:
        return RuleOutcome()

    level = context.fatigue_signal.level
    if level is FatigueLevel.unknown:
        warning = DataWarning(
            rule_id="R-FATIGUE-DATA-01",
            astronaut_id=task.astronaut_id,
            task_id=task.task_id,
            message=(
                f"R-FATIGUE-DATA-01: fatigue level is 'unknown', so rule "
                f"R-FATIGUE-CRITICAL-01 was not evaluated for critical task "
                f"'{task.task_id}'. No conflict was raised."
            ),
        )
        return RuleOutcome(warnings=[warning])

    if level is FatigueLevel.no_flag:
        return RuleOutcome()

    severity = (
        Severity.critical
        if level is FatigueLevel.elevated_concern
        else Severity.high
    )
    alertness_text = (
        "unknown" if task.required_alertness is None else str(task.required_alertness)
    )
    explanation = (
        f"Rule R-FATIGUE-CRITICAL-01: recorded fatigue level is '{level.value}' "
        f"(source '{context.fatigue_signal.source}') and task '{task.task_id}' "
        f"({task.name}) is critical or high-alertness (critical flag="
        f"{task.is_critical}, priority={task.priority.value}, required "
        f"alertness={alertness_text}, threshold "
        f"{config.CRITICAL_TASK_ALERTNESS_REQUIREMENT})."
    )
    suggested_action = (
        "Review the task assignment or timing under rule R-FATIGUE-CRITICAL-01; "
        "rescheduling or adding a recovery opportunity may reduce risk. "
        "Advisory only; final authority remains with the crew, flight surgeon, "
        "and mission control."
    )
    conflict = _build_conflict(
        rule_id="R-FATIGUE-CRITICAL-01",
        conflict_type=ConflictType.high_fatigue_critical_task,
        severity=severity,
        astronaut_id=task.astronaut_id,
        task_ids=[task.task_id],
        affected_start=task.start_time,
        affected_end=task.end_time,
        explanation=explanation,
        suggested_action=suggested_action,
        source_ids=["NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"],
        config_keys=["CRITICAL_TASK_ALERTNESS_REQUIREMENT"],
    )
    return RuleOutcome(conflicts=[conflict])


# ---------------------------------------------------------------------------
# Rule 4: workload_overload
# ---------------------------------------------------------------------------


def workload_overload(
    context: AstronautContext,
    config: MissionConfig = DEFAULT_CONFIG,
) -> RuleOutcome:
    """Flag a workload window with too many demanding tasks or demanding minutes.

    The counting window starts at each demanding task and spans
    ``WORKLOAD_WINDOW_HOURS``. A task is counted when it *starts* inside the
    window. A window is reported once; later windows that only contain a subset
    of an already-reported task set are skipped, which keeps the output stable
    and free of near-duplicates.
    """
    demanding = [
        task
        for task in context.tasks
        if _is_open(task) and _is_demanding(task, config)
    ]
    demanding.sort(key=_sort_key)

    window = timedelta(hours=config.WORKLOAD_WINDOW_HOURS)
    reported: list[frozenset[str]] = []
    conflicts: list[Conflict] = []

    for anchor in demanding:
        window_start = anchor.start_time
        window_end = window_start + window
        group = [
            task
            for task in demanding
            if window_start <= task.start_time < window_end
        ]
        task_ids = frozenset(task.task_id for task in group)
        if any(task_ids <= seen for seen in reported):
            continue

        count = len(group)
        demanding_minutes = sum(
            _overlap_minutes(
                task.start_time, task.end_time, window_start, window_end
            )
            for task in group
        )
        count_exceeded = count > config.MAX_DEMANDING_TASKS_PER_WINDOW
        minutes_exceeded = (
            demanding_minutes > config.MAX_DEMANDING_TASK_HOURS_PER_WINDOW
        )
        if not (count_exceeded or minutes_exceeded):
            continue

        reported.append(task_ids)
        severity = Severity.critical if minutes_exceeded else Severity.high
        ordered_ids = [task.task_id for task in group]
        explanation = (
            f"Rule R-WORKLOAD-01: {count} demanding task(s) start inside the "
            f"{config.WORKLOAD_WINDOW_HOURS} h window "
            f"{window_start.isoformat()} to {window_end.isoformat()}. "
            f"Configured maximum is {config.MAX_DEMANDING_TASKS_PER_WINDOW} "
            f"task(s); cumulative demanding time is {demanding_minutes} min "
            f"against a maximum of "
            f"{config.MAX_DEMANDING_TASK_HOURS_PER_WINDOW} min. Task ids: "
            f"{', '.join(ordered_ids)}."
        )
        suggested_action = (
            "Review redistributing the demanding tasks across the schedule under "
            "rule R-WORKLOAD-01; spreading workload may reduce risk. Advisory "
            "only; mission approval is required."
        )
        conflicts.append(
            _build_conflict(
                rule_id="R-WORKLOAD-01",
                conflict_type=ConflictType.workload_overload,
                severity=severity,
                astronaut_id=context.crew.crew_id,
                task_ids=ordered_ids,
                affected_start=window_start,
                affected_end=window_end,
                explanation=explanation,
                suggested_action=suggested_action,
                source_ids=["NASA-HRP-Sleep-Risk", "NASA-STD-3001-Vol2"],
                config_keys=[
                    "WORKLOAD_WINDOW_HOURS",
                    "MAX_DEMANDING_TASKS_PER_WINDOW",
                    "MAX_DEMANDING_TASK_HOURS_PER_WINDOW",
                    "DEMANDING_WORKLOAD_LEVELS",
                    "CRITICAL_TASK_ALERTNESS_REQUIREMENT",
                ],
            )
        )

    return RuleOutcome(conflicts=conflicts)


# ---------------------------------------------------------------------------
# Rule 5: circadian_misalignment
# ---------------------------------------------------------------------------


def _minute_of_day(value: datetime) -> int:
    """Return the UTC minute-of-day for an aware datetime."""
    return value.hour * 60 + value.minute


def _arcs_overlap(
    first_start: int, first_duration: int, second_start: int, second_duration: int
) -> bool:
    """Return True when two circular minute-of-day intervals overlap.

    Intervals are half-open and may cross midnight. A duration of one full day
    overlaps everything; a non-positive duration overlaps nothing.
    """
    if first_duration <= 0 or second_duration <= 0:
        return False
    if first_duration >= _MINUTES_PER_DAY or second_duration >= _MINUTES_PER_DAY:
        return True

    def inside(point: int, start: int, duration: int) -> bool:
        return (point - start) % _MINUTES_PER_DAY < duration

    return inside(first_start, second_start, second_duration) or inside(
        second_start, first_start, first_duration
    )


def _clock_text(task: TaskView) -> str:
    """Render a task's UTC clock placement, handling midnight crossing."""
    start = task.start_time.strftime("%H:%M")
    end = (task.start_time + timedelta(minutes=max(1, task.duration_minutes))).strftime(
        "%H:%M"
    )
    return f"{start}-{end} UTC"


def circadian_misalignment(
    context: AstronautContext,
    task: TaskView,
    config: MissionConfig = DEFAULT_CONFIG,
) -> RuleOutcome:
    """Flag a wake task placed inside sleep time or the circadian trough.

    The rule checks the task's clock placement (minute of day), not its calendar
    date, so a recurring pattern is detected even on a day without an explicit
    sleep window:

    * habitual sleep period - the clock interval of any planned/inferred sleep
      window, or the configurable ``PROTECTED_SLEEP_WINDOW_*`` fallback when no
      window exists;
    * WOCL - ``WOCL_START_HOUR`` to ``WOCL_END_HOUR`` expanded by
      ``WOCL_TOLERANCE_MINUTES``.

    Sleep, rest, and recovery tasks are exempt. The WOCL and the habitual sleep
    pattern are simplifications: all times are UTC and crew-local time zones are
    not modelled.
    """
    if _is_protected(task):
        return RuleOutcome()

    start = _minute_of_day(task.start_time)
    duration = max(1, min(task.duration_minutes, _MINUTES_PER_DAY))
    reasons: list[str] = []
    config_keys: list[str] = []

    if context.planned_sleep_windows:
        for window in context.planned_sleep_windows:
            if _arcs_overlap(
                start,
                duration,
                _minute_of_day(window.start_time),
                window.duration_minutes,
            ):
                reasons.append(
                    f"inside the habitual sleep period "
                    f"{window.start_time.strftime('%H:%M')}-"
                    f"{window.end_time.strftime('%H:%M')} UTC "
                    f"({window.source})"
                )
                config_keys.extend(
                    [
                        "HABITUAL_SLEEP_MIN_RECORDS",
                        "HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES",
                    ]
                )
                break
    else:
        fallback_start = config.PROTECTED_SLEEP_WINDOW_START_HOUR * 60
        fallback_duration = (
            config.PROTECTED_SLEEP_WINDOW_END_HOUR * 60 - fallback_start
        ) % _MINUTES_PER_DAY
        if _arcs_overlap(start, duration, fallback_start, fallback_duration):
            reasons.append(
                f"inside the configurable protected sleep window "
                f"{config.PROTECTED_SLEEP_WINDOW_START_HOUR:02d}:00-"
                f"{config.PROTECTED_SLEEP_WINDOW_END_HOUR:02d}:00 UTC "
                f"(fallback; no inferred window)"
            )
            config_keys.extend(
                [
                    "PROTECTED_SLEEP_WINDOW_START_HOUR",
                    "PROTECTED_SLEEP_WINDOW_END_HOUR",
                ]
            )

    wocl_duration = (config.WOCL_END_HOUR - config.WOCL_START_HOUR) * 60 % (
        _MINUTES_PER_DAY
    )
    wocl_start = (
        config.WOCL_START_HOUR * 60 - config.WOCL_TOLERANCE_MINUTES
    ) % _MINUTES_PER_DAY
    wocl_duration = min(
        _MINUTES_PER_DAY,
        wocl_duration + 2 * config.WOCL_TOLERANCE_MINUTES,
    )
    if _arcs_overlap(start, duration, wocl_start, wocl_duration):
        reasons.append(
            f"inside the configurable WOCL "
            f"{config.WOCL_START_HOUR:02d}:00-{config.WOCL_END_HOUR:02d}:00 UTC "
            f"with {config.WOCL_TOLERANCE_MINUTES} min tolerance"
        )
        config_keys.extend(
            ["WOCL_START_HOUR", "WOCL_END_HOUR", "WOCL_TOLERANCE_MINUTES"]
        )

    if not reasons:
        return RuleOutcome()

    severity = _severity_for_task(task)
    if severity is Severity.high and (
        task.required_alertness is None
        or task.required_alertness < config.CRITICAL_TASK_ALERTNESS_REQUIREMENT
    ):
        severity = Severity.medium

    explanation = (
        f"Rule R-CIRCADIAN-01: task '{task.task_id}' ({task.name}) has clock "
        f"placement {_clock_text(task)}, which is "
        f"{' and '.join(reasons)}. All times are UTC and the clock window is a "
        "configurable assumption."
    )
    suggested_action = (
        "Review task timing under rule R-CIRCADIAN-01; scheduling high-alertness "
        "work outside the circadian trough may reduce risk. Advisory only; "
        "mission approval is required."
    )
    conflict = _build_conflict(
        rule_id="R-CIRCADIAN-01",
        conflict_type=ConflictType.circadian_low_alertness,
        severity=severity,
        astronaut_id=task.astronaut_id,
        task_ids=[task.task_id],
        affected_start=task.start_time,
        affected_end=task.end_time,
        explanation=explanation,
        suggested_action=suggested_action,
        source_ids=["NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"],
        config_keys=config_keys,
    )
    return RuleOutcome(conflicts=[conflict])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def detect_conflicts(
    context: AstronautContext,
    config: MissionConfig = DEFAULT_CONFIG,
) -> ConflictReport:
    """Run every rule for one astronaut and return a deterministic report.

    Completed and cancelled tasks are skipped. Conflicts are ordered by affected
    start, then severity (highest first), then conflict id. Data warnings are
    ordered by rule id, task id, and message.

    Raises:
        ValueError: if ``context.tasks`` contains a task that belongs to another
            astronaut; a context is single-crew by contract.
    """
    for task in context.tasks:
        if task.astronaut_id != context.crew.crew_id:
            raise ValueError(
                "context.tasks contains a task for another astronaut: "
                f"{task.task_id!r} belongs to {task.astronaut_id!r}, not "
                f"{context.crew.crew_id!r}"
            )

    tasks = sorted(
        (task for task in context.tasks if _is_open(task)), key=_sort_key
    )
    conflicts: list[Conflict] = []
    warnings: list[DataWarning] = []

    per_task_rules = (
        sleep_mission_conflict,
        insufficient_recovery,
        high_fatigue_before_critical,
        circadian_misalignment,
    )
    for task in tasks:
        for rule in per_task_rules:
            outcome = rule(context, task, config)
            conflicts.extend(outcome.conflicts)
            warnings.extend(outcome.warnings)

    workload_outcome = workload_overload(context, config)
    conflicts.extend(workload_outcome.conflicts)
    warnings.extend(workload_outcome.warnings)

    if not context.planned_sleep_windows:
        warnings.append(
            DataWarning(
                rule_id="R-DATA-SLEEP-WINDOW",
                astronaut_id=context.crew.crew_id,
                task_id=None,
                message=(
                    "R-DATA-SLEEP-WINDOW: no planned or inferred sleep window is "
                    "available; R-SLEEP-WINDOW-01 was not checked. "
                    "R-CIRCADIAN-01 used the configurable fallback window."
                ),
            )
        )
    if _latest_sleep(context) is None:
        warnings.append(
            DataWarning(
                rule_id="R-DATA-SLEEP-RECORD",
                astronaut_id=context.crew.crew_id,
                task_id=None,
                message=(
                    "R-DATA-SLEEP-RECORD: no recent sleep record is available; "
                    "the short-sleep part of R-RECOVERY-02 was skipped."
                ),
            )
        )

    ordered_conflicts = sorted(
        conflicts,
        key=lambda conflict: (
            conflict.affected_start,
            -_SEVERITY_RANK[conflict.severity],
            conflict.conflict_id,
        ),
    )
    ordered_warnings = sorted(
        warnings,
        key=lambda warning: (
            warning.rule_id,
            warning.task_id or "",
            warning.message,
        ),
    )
    config_keys = sorted(
        {key for conflict in ordered_conflicts for key in conflict.config_keys}
    )
    return ConflictReport(
        astronaut_id=context.crew.crew_id,
        rule_set_version=RULE_SET_VERSION,
        conflicts=ordered_conflicts,
        data_warnings=ordered_warnings,
        config_keys=config_keys,
    )
