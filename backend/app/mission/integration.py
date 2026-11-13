"""Task-suitability rules for mission intelligence.

The rules are deliberately narrow. A task is judged only on these four input
families, all supplied by ``AstronautContext`` and the ``TaskView``:

1. the categorical fatigue signal level;
2. the most recent recorded sleep duration compared with the crew sleep target;
3. the task's required alertness, priority, workload, and criticality;
4. overlap with an inferred/planned sleep window.

No numeric fatigue score is invented, and no database access happens here.
If a required input is missing (unknown fatigue, no sleep record, unusable
sleep target) the result is ``insufficient_data`` with the missing inputs
named. The rules never fall back to a "probably fine" answer.

Rule ids (proposed system logic, Phase 3):

* ``R-DATA-01`` - required input missing, no judgement made.
* ``R-FATIGUE-01`` - elevated concern + demanding task -> not recommended.
* ``R-FATIGUE-02`` - elevated concern + non-demanding task -> review.
* ``R-FATIGUE-03`` - monitor + demanding task -> review.
* ``R-FATIGUE-04`` - monitor + non-demanding task -> review (low).
* ``R-SLEEP-01`` - last sleep below the severe-shortfall ratio -> not recommended
  for demanding tasks, review otherwise.
* ``R-SLEEP-02`` - last sleep below the review ratio but above the severe ratio,
  on a demanding task -> review.
* ``R-SLEEP-03`` - task overlaps a planned sleep window -> not recommended.
  Sleep/rest/recovery tasks are exempt because occupying a sleep window is the
  point of those tasks.
* ``R-OK-01`` - no rule triggered.

Every threshold comes from ``MissionConfig``; the values are configurable
assumptions, not NASA cut-offs.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.models import (
    AstronautContext,
    FatigueLevel,
    PlannedSleepWindow,
    Priority,
    SuitabilityResult,
    SuitabilityStatus,
    TaskStatus,
    TaskView,
)
from app.mission.schedule import RECOVERY_CATEGORIES, SLEEP_CATEGORIES

_SEVERITY_REVIEW_LOW = 1
_SEVERITY_REVIEW = 2
_SEVERITY_NOT_RECOMMENDED = 3

_PROTECTED_SLEEP_CATEGORIES = SLEEP_CATEGORIES | RECOVERY_CATEGORIES
"""Categories that are allowed to occupy a planned sleep window."""


@dataclass(frozen=True)
class _Finding:
    """One triggered rule with its advisory weight."""

    severity: int
    rule_id: str
    reason: str


def _percent(ratio: float) -> str:
    """Format a ratio as a whole percentage."""
    return f"{ratio * 100:.0f}%"


def _latest_sleep(context: AstronautContext):
    """Return the most recent sleep summary, or ``None`` when there is none."""
    return max(
        context.recent_sleep,
        key=lambda summary: (summary.end_time, summary.sleep_id),
        default=None,
    )


def _is_demanding(task: TaskView, config: MissionConfig) -> bool:
    """Return True when the task demands high alertness or is critical.

    The test is deliberately broad: critical flag, critical priority, a
    configured demanding workload level, or a required alertness at or above
    ``CRITICAL_TASK_ALERTNESS_REQUIREMENT``.
    """
    if task.is_critical or task.priority is Priority.critical:
        return True
    if task.workload_level in config.DEMANDING_WORKLOAD_LEVELS:
        return True
    return (
        task.required_alertness is not None
        and task.required_alertness >= config.CRITICAL_TASK_ALERTNESS_REQUIREMENT
    )


def _is_protected_sleep_task(task: TaskView) -> bool:
    """Return True for sleep/rest/recovery tasks that may occupy a sleep window."""
    return task.category in _PROTECTED_SLEEP_CATEGORIES


def _overlapping_sleep_windows(
    task: TaskView, context: AstronautContext
) -> list[PlannedSleepWindow]:
    """Return planned sleep windows that overlap the half-open task interval."""
    return [
        window
        for window in context.planned_sleep_windows
        if task.start_time < window.end_time and window.start_time < task.end_time
    ]


def _format_windows(windows: list[PlannedSleepWindow]) -> str:
    """Render windows for a human-readable reason."""
    return ", ".join(
        f"{window.start_time.isoformat()} to {window.end_time.isoformat()}"
        for window in windows
    )


def _thresholds(config: MissionConfig) -> dict[str, object]:
    """Return the threshold snapshot recorded in ``inputs_used``."""
    return {
        "SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO": (
            config.SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO
        ),
        "SLEEP_SHORTFALL_REVIEW_RATIO": config.SLEEP_SHORTFALL_REVIEW_RATIO,
        "CRITICAL_TASK_ALERTNESS_REQUIREMENT": (
            config.CRITICAL_TASK_ALERTNESS_REQUIREMENT
        ),
        "DEMANDING_WORKLOAD_LEVELS": [
            level.value for level in config.DEMANDING_WORKLOAD_LEVELS
        ],
    }


def evaluate_suitability(
    context: AstronautContext,
    task: TaskView,
    config: MissionConfig = DEFAULT_CONFIG,
) -> SuitabilityResult:
    """Evaluate one task against one astronaut's current context.

    Raises:
        ValueError: if ``task`` does not belong to ``context.crew``.
    """
    if task.astronaut_id != context.crew.crew_id:
        raise ValueError(
            "task astronaut_id does not match the context crew: "
            f"{task.astronaut_id!r} != {context.crew.crew_id!r}"
        )

    latest_sleep = _latest_sleep(context)
    last_sleep_minutes = (
        latest_sleep.duration_minutes if latest_sleep is not None else None
    )
    target_minutes = int(round(context.crew.sleep_target_hours * 60))
    ratio = (
        last_sleep_minutes / target_minutes
        if last_sleep_minutes is not None and target_minutes > 0
        else None
    )

    demanding = _is_demanding(task, config)
    overlapping_windows = _overlapping_sleep_windows(task, context)
    overlaps_planned_sleep = bool(overlapping_windows)
    protected_sleep_task = _is_protected_sleep_task(task)

    inputs_used: dict[str, object] = {
        "fatigue_level": context.fatigue_signal.level.value,
        "last_sleep_minutes": last_sleep_minutes,
        "sleep_target_minutes": target_minutes,
        "sleep_ratio": None if ratio is None else round(ratio, 3),
        "required_alertness": task.required_alertness,
        "priority": task.priority.value,
        "workload_level": task.workload_level.value,
        "is_critical": task.is_critical,
        "demanding": demanding,
        "overlaps_planned_sleep": overlaps_planned_sleep,
        "protected_sleep_task": protected_sleep_task,
        "thresholds": _thresholds(config),
    }

    missing: list[str] = []
    if context.fatigue_signal.level is FatigueLevel.unknown:
        missing.append("fatigue_signal.level")
    if latest_sleep is None:
        missing.append("recent_sleep")
    if target_minutes <= 0:
        missing.append("crew.sleep_target_hours")
    if missing:
        return SuitabilityResult(
            task_id=task.task_id,
            astronaut_id=task.astronaut_id,
            status=SuitabilityStatus.insufficient_data,
            reasons=[
                "R-DATA-01: missing required input(s): "
                f"{', '.join(missing)}; no suitability judgement is made."
            ],
            rule_ids=["R-DATA-01"],
            inputs_used={**inputs_used, "missing_inputs": missing},
        )

    # The guard above makes both values usable.
    assert last_sleep_minutes is not None and ratio is not None

    findings: list[_Finding] = []

    fatigue_level = context.fatigue_signal.level
    if fatigue_level is FatigueLevel.elevated_concern:
        if demanding:
            findings.append(
                _Finding(
                    _SEVERITY_NOT_RECOMMENDED,
                    "R-FATIGUE-01",
                    "Fatigue level 'elevated_concern' combined with a demanding "
                    "task is not recommended.",
                )
            )
        else:
            findings.append(
                _Finding(
                    _SEVERITY_REVIEW,
                    "R-FATIGUE-02",
                    "Fatigue level 'elevated_concern' warrants review even for a "
                    "non-demanding task.",
                )
            )
    elif fatigue_level is FatigueLevel.monitor:
        if demanding:
            findings.append(
                _Finding(
                    _SEVERITY_REVIEW,
                    "R-FATIGUE-03",
                    "Fatigue level 'monitor' combined with a demanding task "
                    "warrants review.",
                )
            )
        else:
            findings.append(
                _Finding(
                    _SEVERITY_REVIEW_LOW,
                    "R-FATIGUE-04",
                    "Fatigue level 'monitor' is noted for this non-demanding task.",
                )
            )

    if ratio < config.SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO:
        findings.append(
            _Finding(
                _SEVERITY_NOT_RECOMMENDED if demanding else _SEVERITY_REVIEW,
                "R-SLEEP-01",
                f"Last sleep {last_sleep_minutes} min is {_percent(ratio)} of the "
                f"{target_minutes} min target, below the "
                f"{_percent(config.SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO)} "
                "not-recommended ratio.",
            )
        )
    elif ratio < config.SLEEP_SHORTFALL_REVIEW_RATIO and demanding:
        findings.append(
            _Finding(
                _SEVERITY_REVIEW,
                "R-SLEEP-02",
                f"Last sleep {last_sleep_minutes} min is {_percent(ratio)} of the "
                f"{target_minutes} min target, below the "
                f"{_percent(config.SLEEP_SHORTFALL_REVIEW_RATIO)} review ratio "
                "for a demanding task.",
            )
        )

    if overlaps_planned_sleep and not protected_sleep_task:
        findings.append(
            _Finding(
                _SEVERITY_NOT_RECOMMENDED,
                "R-SLEEP-03",
                "Task overlaps planned sleep window(s): "
                f"{_format_windows(overlapping_windows)}.",
            )
        )

    if not findings:
        return SuitabilityResult(
            task_id=task.task_id,
            astronaut_id=task.astronaut_id,
            status=SuitabilityStatus.suitable,
            reasons=["R-OK-01: no configured suitability rule was triggered."],
            rule_ids=["R-OK-01"],
            inputs_used=inputs_used,
        )

    ordered = sorted(findings, key=lambda finding: (-finding.severity, finding.rule_id))
    status = (
        SuitabilityStatus.not_recommended
        if ordered[0].severity >= _SEVERITY_NOT_RECOMMENDED
        else SuitabilityStatus.review
    )
    return SuitabilityResult(
        task_id=task.task_id,
        astronaut_id=task.astronaut_id,
        status=status,
        reasons=[f"{finding.rule_id}: {finding.reason}" for finding in ordered],
        rule_ids=list(dict.fromkeys(finding.rule_id for finding in ordered)),
        inputs_used=inputs_used,
    )


def evaluate_upcoming(
    context: AstronautContext, config: MissionConfig = DEFAULT_CONFIG
) -> list[SuitabilityResult]:
    """Evaluate every not-completed, not-cancelled task in the context.

    Results follow task start order (ties broken by task id). Tasks whose status
    is ``completed`` or ``cancelled`` are skipped because they are no longer
    upcoming.
    """
    results: list[SuitabilityResult] = []
    for task in sorted(
        context.tasks, key=lambda item: (item.start_time, item.task_id)
    ):
        if task.status in (TaskStatus.completed, TaskStatus.cancelled):
            continue
        results.append(evaluate_suitability(context, task, config))
    return results
